"""阿里云百炼 · Tripo 3D 生成（3D 主通道）。

接口要点（已按官方文档核实，2026-10）：

- 创建任务：``POST {base}/api/v1/services/aigc/video-generation/3d-generation``
- 轮询任务：``GET {base}/api/v1/tasks/{task_id}``
- 请求头必须带 ``X-DashScope-Async: enable``（缺失会报"不支持同步调用"）
- ``base`` 形如 ``https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com``，
  **仅华北2（北京）地域可用**，且必须使用该地域的 Key
- 输入三选一互斥：``prompt``（文生）/ ``image``（单图，公网 URL）/
  ``images``（多图，前/左/后/右 4 视角）
- 输出：``results[].pbr_model_url``（GLB，PBR 材质）或 ``base_model_url``（无贴图 GLB）
- 产物链接 **2 小时**过期，必须即时落盘；``task_id`` 有效期 24 小时
- 官方建议轮询间隔 15 秒，查询接口 RPS 上限 20
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ..client import cloud_client
from .base import BaseCloudModel

log = logging.getLogger("adapters.cloud_backends.bailian_tripo")

__all__ = ["BailianTripoModel", "MODEL_OPTIONS", "DEFAULT_MODEL"]

#: 可选模型：H3.1 精度更高且单价更低，P1.0 胜在速度
MODEL_OPTIONS = ("Tripo/Tripo-H3.1", "Tripo/Tripo-P1.0")
DEFAULT_MODEL = "Tripo/Tripo-H3.1"

CREATE_PATH = "/api/v1/services/aigc/video-generation/3d-generation"
TASK_PATH = "/api/v1/tasks/{task_id}"

DONE_STATES = ("succeeded",)
FAILED_STATES = ("failed", "canceled", "cancelled", "unknown")

#: 下载链接有效期 2 小时，留 1 小时余量做缓存 TTL 上限判断
URL_TTL_SECONDS = 2 * 3600


class BailianTripoModel(BaseCloudModel):
    """百炼托管的 Tripo 3D 生成。

    凭据复用模型广场的 DashScope Key；``workspace_id`` 无法复用，必须单独配置。
    """

    PROVIDER = "bailian-tripo"
    DEFAULT_MODEL = DEFAULT_MODEL
    OUTPUT_EXT = "glb"
    ENV_KEY = "DASHSCOPE_API_KEY"
    #: 文档建议 15 秒轮询；生成耗时通常数分钟
    DEFAULT_TASK_TIMEOUT = 1800.0

    def __init__(
        self,
        *,
        workspace_id: str = "",
        uploader: Callable[[bytes, str], str] | None = None,
        texture_quality: str = "standard",
        geometry_quality: str = "standard",
        pbr: bool = True,
        texture: bool = True,
        poll_interval: float = 15.0,
        **kwargs,
    ):
        super().__init__(poll_interval=poll_interval, **kwargs)
        self.workspace_id = (workspace_id or "").strip()
        #: 本地上传回调（``bytes, 建议文件名 -> 公网 URL``）。百炼只接受公网 URL，
        #: 由调用方注入项目已有的对象存储能力；未注入时本地图片走明确报错。
        self._uploader = uploader
        self.texture_quality = texture_quality
        self.geometry_quality = geometry_quality
        self.pbr = pbr
        self.texture = texture

    # ── 请求构造 ──────────────────────────────────────────────────────────

    def _resolve_base(self) -> str:
        base = (self.api_base or "").rstrip("/")
        if not base:
            raise cloud_client.CloudAPIRequestError(
                "百炼通道未配置 base_url", provider=self.PROVIDER
            )
        if "{workspace_id}" in base:
            if not self.workspace_id:
                raise cloud_client.CloudAPIRequestError(
                    "百炼通道缺少 workspace_id（业务空间 ID），" "请在云能力面板填写后重试",
                    provider=self.PROVIDER,
                )
            base = base.replace("{workspace_id}", self.workspace_id)
        if "cn-beijing" not in base:
            log.warning("[bailian-tripo] base_url 不含 cn-beijing，3D 生成仅华北2地域可用")
        return base

    def _resolve_image_url(
        self, image: Any, image_url: Optional[str], image_name: str
    ) -> Optional[str]:
        """百炼只吃公网 URL；本地字节需经 uploader 换取 URL。"""

        if image_url:
            return image_url
        if image is None:
            return None
        if isinstance(image, str) and image.startswith(("http://", "https://")):
            return image
        if self._uploader is None:
            raise cloud_client.CloudAPIRequestError(
                "百炼 3D 通道只接受公网图片 URL；本地上传需接入对象存储"
                "（在算子层注入 uploader）",
                provider=self.PROVIDER,
            )
        return self._uploader(image, image_name)

    def _build_payload(
        self,
        *,
        prompt: Optional[str],
        image_url: Optional[str],
        images: Optional[list],
        provider_kwargs: dict,
    ) -> dict:
        inputs: dict[str, Any] = {}
        if images:
            inputs["images"] = images
        elif image_url:
            inputs["image"] = image_url
        elif prompt:
            inputs["prompt"] = prompt
        else:
            raise ValueError("BailianTripoModel 需要 prompt / image / image_url / images 之一")

        parameters: dict[str, Any] = {
            "texture_quality": self.texture_quality,
            "pbr": self.pbr,
            "texture": self.texture,
        }
        # geometry_quality 只对 H3.1 生效，P1.0 传了会被忽略
        if self.geometry_quality != "standard":
            parameters["geometry_quality"] = self.geometry_quality
        parameters.update(provider_kwargs)

        return {"model": self.model, "input": inputs, "parameters": parameters}

    # ── 结果解析 ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_result(task: dict) -> dict:
        """取 ``results`` 中第一条可用产物；失败条目优先报错。"""

        results = task.get("results")
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                if item.get("pbr_model_url") or item.get("base_model_url"):
                    return item
            for item in results:
                if isinstance(item, dict) and (item.get("code") or item.get("message")):
                    raise cloud_client.CloudTaskFailed(
                        f"百炼 3D 任务失败：{item.get('message') or item.get('code')}",
                        provider="bailian-tripo",
                        payload=item,
                    )
        raise cloud_client.CloudAPIError(
            f"任务已成功但没有模型 URL：results={results!r}",
            provider="bailian-tripo",
            payload=task,
        )

    # ── 推理 ──────────────────────────────────────────────────────────────

    def infer(
        self,
        *,
        prompt: Optional[str] = None,
        image: Any = None,
        image_url: Optional[str] = None,
        images: Optional[list] = None,
        image_name: str = "input.png",
        seed: int | None = None,
        decimation_target: int | None = None,
        texture_size: int | None = None,
        **provider_kwargs,
    ) -> bytes:
        """生成一个 3D 资产并返回 GLB 字节。

        Args:
            prompt: 文生 3D 提示词（≤1024 字符，中英文均可）。
            image: 单图输入（公网 URL 字符串，或经 ``uploader`` 上传的本地字节）。
            image_url: 单图输入的公网 URL。
            images: 多图输入（前/左/后/右 4 项，项形如
                ``{"type": "png", "file_token": "<url>"}``，缺的视角传 ``{}``）。
            seed / decimation_target / texture_size: 百炼接口无对应参数，
                **仅记录不发送**（由算子层决定是否需要本地后处理）。
        """
        resolved_url = self._resolve_image_url(image, image_url, image_name)
        payload = self._build_payload(
            prompt=prompt,
            image_url=resolved_url,
            images=images,
            provider_kwargs=provider_kwargs,
        )
        # 复用过滤器会把 image_url 纳进来，保证同图同参命中缓存
        cache_key = self._cache_key(
            payload=payload, image_url=resolved_url or "", images=images or []
        )
        cached = self._cache.get(cache_key, ext=self.OUTPUT_EXT)
        if cached is not None:
            self.last_call_info = {
                "provider": self.PROVIDER,
                "model": self.model,
                "cached": True,
                "cache_key": cache_key,
                "bytes": len(cached),
            }
            return cached

        ignored = {
            name: value
            for name, value in (
                ("seed", seed),
                ("decimation_target", decimation_target),
                ("texture_size", texture_size),
            )
            if value is not None
        }
        if ignored:
            log.info("[bailian-tripo] 接口无对应参数，已忽略：%s", sorted(ignored))

        base = self._resolve_base()
        client = self.client
        # 任务接口挂在业务空间域名下，与通用 base 同源
        client.base_url = base

        created = client.request(
            "POST",
            CREATE_PATH,
            json_body=payload,
            headers=self._headers({"X-DashScope-Async": "enable"}),
        )
        task_id = str((created.get("output") or {}).get("task_id") or created.get("task_id") or "")
        if not task_id:
            raise cloud_client.CloudAPIError(
                f"创建任务成功但未返回 task_id：{created!r}", provider=self.PROVIDER
            )

        task = cloud_client.poll_task(
            lambda: client.request("GET", TASK_PATH.format(task_id=task_id)),
            task_id=task_id,
            timeout=self.task_timeout,
            poll_interval=self.poll_interval,
            done_states=DONE_STATES,
            failed_states=FAILED_STATES,
            provider=self.PROVIDER,
            sleep=self._sleep,
        )

        result = self._extract_result(task)
        url = result.get("pbr_model_url") or result.get("base_model_url")
        data = self._fetch_bytes(str(url), cache_key)

        usage = task.get("usage") or {}
        self.last_call_info.update(
            {
                "provider": self.PROVIDER,
                "model": self.model,
                "task_id": task_id,
                "cached": False,
                "cache_key": cache_key,
                "bytes": len(data),
                "ignored_params": sorted(ignored),
                "preview_url": result.get("rendered_image_url"),
                "task_type": usage.get("3d_task_type"),
                "url_ttl_seconds": URL_TTL_SECONDS,
            }
        )
        log.info(
            "[bailian-tripo] task=%s model=%s bytes=%s",
            task_id,
            self.model,
            len(data),
        )
        return data
