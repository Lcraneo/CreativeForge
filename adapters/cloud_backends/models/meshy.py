"""Meshy 官方 API（3D 最终兜底通道）。

定位说明：仅在百炼与 Tripo 官方都失败时启用。免费档的产物是
**CC BY 4.0（需署名 Meshy）**，若要对外发行且可能用到本通道产物，
需要在发布说明中加署名或升级到付费档。

与另两条通道的差异：

- 单图输入走 **base64 data URI**（无独立上传接口）
- 文生 3D 是两段式：``preview`` 出几何 → ``refine`` 上贴图（两次计费）
- 输出格式最全：GLB / FBX / OBJ / USDZ / STL
- ``target_polycount`` 允许范围 100–300000
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..client import cloud_client
from .base import BaseCloudModel, glb_triangles, image_to_data_uri

log = logging.getLogger("adapters.cloud_backends.meshy")

__all__ = ["MeshyModel", "MODEL_OPTIONS", "DEFAULT_MODEL", "SUPPORTED_FORMATS"]

MODEL_OPTIONS = ("meshy-6", "meshy-5")
DEFAULT_MODEL = "meshy-6"

DONE_STATES = ("succeeded", "success", "completed")
FAILED_STATES = ("failed", "canceled", "cancelled", "expired")

SUPPORTED_FORMATS = ("glb", "fbx", "obj", "usdz", "stl", "mtl", "3mf")

#: 服务端接受的目标面数范围（超出即终态 400）
POLYCOUNT_RANGE = (100, 300_000)


class MeshyModel(BaseCloudModel):
    """Meshy image-to-3D / text-to-3D。"""

    PROVIDER = "meshy"
    DEFAULT_MODEL = DEFAULT_MODEL
    OUTPUT_EXT = "glb"
    ENV_KEY = "MESHY_API_KEY"
    DEFAULT_TASK_TIMEOUT = 1800.0

    def __init__(
        self,
        *,
        output_format: str = "glb",
        texture: bool = True,
        enable_pbr: bool = True,
        topology: str = "triangle",
        should_remesh: bool | None = None,
        low_poly: bool = False,
        refine: bool = True,
        poll_interval: float = 3.0,
        **kwargs,
    ):
        super().__init__(poll_interval=poll_interval, **kwargs)
        fmt = (output_format or "glb").lower().lstrip(".")
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(f"output_format={fmt!r} 不在支持列表 {SUPPORTED_FORMATS}")
        self.output_format = fmt
        self.OUTPUT_EXT = fmt
        self.texture = texture
        self.enable_pbr = enable_pbr
        self.topology = topology
        self.should_remesh = should_remesh
        self.low_poly = low_poly
        self.refine = refine

    # ── 工具 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_png_bytes(image: Any) -> bytes | None:
        if image is None:
            return None
        if isinstance(image, (bytes, bytearray)):
            return bytes(image)
        try:
            import io

            from PIL import Image

            buffer = io.BytesIO()
            if isinstance(image, Image.Image):
                image.convert("RGBA").save(buffer, format="PNG")
            else:
                Image.fromarray(image).convert("RGBA").save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as error:  # noqa: BLE001 - 输入类型不可控
            raise ValueError(
                f"无法把 {type(image).__name__} 转成 PNG，请传 bytes 或 PIL.Image"
            ) from error

    def _clamp_polycount(self, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        low, high = POLYCOUNT_RANGE
        clamped = max(low, min(int(value), high))
        if clamped != int(value):
            log.warning(
                "[meshy] target_polycount %s 收敛到 %s（接口范围 %s-%s）",
                value,
                clamped,
                low,
                high,
            )
        return clamped

    @staticmethod
    def _task_id_of(resp: Any) -> str:
        if isinstance(resp, dict):
            for key in ("result", "id", "task_id"):
                value = resp.get(key)
                if isinstance(value, str) and value:
                    return value
        raise cloud_client.CloudAPIError(f"Meshy 未返回任务 ID：{resp!r}", provider="meshy")

    def _fetch_task(self, endpoint: str, task_id: str) -> dict:
        task = self.client.request("GET", f"{endpoint}/{task_id}")
        if not isinstance(task, dict):
            raise cloud_client.CloudAPIError(
                f"任务响应不是对象：{task!r}", provider=self.PROVIDER, task_id=task_id
            )
        return task

    def _model_url(self, task: dict) -> str:
        urls = task.get("model_urls") or {}
        url = urls.get(self.output_format)
        if isinstance(url, str) and url.startswith("http"):
            return url
        raise cloud_client.CloudAPIError(
            f"任务完成但没有 {self.output_format!r} 产物，可用格式：{sorted(urls)}",
            provider=self.PROVIDER,
            task_id=str(task.get("id") or ""),
        )

    def _submit_and_wait(self, endpoint: str, payload: dict, task_ids: list[str]) -> dict:
        created = self.client.request("POST", endpoint, json_body=payload)
        task_id = self._task_id_of(created)
        task_ids.append(task_id)
        return cloud_client.poll_task(
            lambda: self._fetch_task(endpoint, task_id),
            task_id=task_id,
            timeout=self.task_timeout,
            poll_interval=self.poll_interval,
            done_states=DONE_STATES,
            failed_states=FAILED_STATES,
            status_key="status",
            provider=self.PROVIDER,
            sleep=self._sleep,
        )

    # ── 推理 ──────────────────────────────────────────────────────────────

    def infer(
        self,
        *,
        prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        image: Any = None,
        image_url: Optional[str] = None,
        seed: int | None = None,
        decimation_target: int | None = None,
        texture_size: int | None = None,
        **provider_kwargs,
    ) -> bytes:
        """生成 3D 资产并返回指定格式字节。"""

        if negative_prompt:
            raise ValueError(
                "Meshy 没有 negative_prompt 参数，请把约束写进 prompt，" "或改用 Tripo 通道"
            )
        if texture_size is not None:
            log.debug("[meshy] texture_size=%s 无对应参数，已忽略", texture_size)

        png = self._to_png_bytes(image)
        use_image = png is not None or bool(image_url)
        if not use_image and not prompt:
            raise ValueError("需要 image / image_url / prompt 之一")

        polycount = self._clamp_polycount(decimation_target)
        payload: dict[str, Any] = {
            "ai_model": self.model,
            "model_type": "lowpoly" if self.low_poly else "standard",
            "topology": self.topology,
        }
        if polycount is not None:
            payload["target_polycount"] = polycount
        if self.should_remesh is not None:
            payload["should_remesh"] = self.should_remesh

        if use_image:
            payload["should_texture"] = self.texture
            payload["enable_pbr"] = self.enable_pbr
        else:
            payload["mode"] = "preview"
            payload["prompt"] = prompt
            if seed is not None:
                payload["seed"] = int(seed)
        payload.update(provider_kwargs)

        cache_key = self._cache_key(
            payload=payload,
            image_sha256=cloud_client.bytes_hash(png),
            image_url=image_url or "",
            refine=self.refine and self.texture and not use_image,
            output_format=self.output_format,
        )
        cached = self._cache.get(cache_key, ext=self.output_format)
        if cached is not None:
            self.last_call_info = {
                "provider": self.PROVIDER,
                "model": self.model,
                "cached": True,
                "cache_key": cache_key,
                "bytes": len(cached),
            }
            if self.OUTPUT_EXT == "glb":
                triangles = glb_triangles(cached)
                if triangles is not None:
                    self.last_call_info["triangles"] = triangles
            return cached

        task_ids: list[str] = []
        if use_image:
            endpoint = "/openapi/v1/image-to-3d"
            payload["image_url"] = image_url if png is None else image_to_data_uri(png)
            task = self._submit_and_wait(endpoint, payload, task_ids)
        else:
            endpoint = "/openapi/v2/text-to-3d"
            task = self._submit_and_wait(endpoint, payload, task_ids)
            if self.texture and self.refine:
                # 第二段计费任务：preview 只有几何，refine 才上贴图
                refine_payload = {
                    "mode": "refine",
                    "preview_task_id": task_ids[-1],
                    "ai_model": self.model,
                    "enable_pbr": self.enable_pbr,
                }
                task = self._submit_and_wait(endpoint, refine_payload, task_ids)

        data = self._fetch_bytes(self._model_url(task), cache_key)
        info: dict[str, Any] = {
            "provider": self.PROVIDER,
            "model": self.model,
            "task_id": task_ids[-1],
            "task_ids": task_ids,
            "cached": False,
            "cache_key": cache_key,
            "bytes": len(data),
            "format": self.output_format,
            "credits": task.get("credits_consumed", task.get("credits")),
            "preview_url": task.get("thumbnail_url"),
            "license_note": "免费档产物为 CC BY 4.0，需署名 Meshy",
        }
        if self.OUTPUT_EXT == "glb":
            # GF glb_summary 同口径：面数写入 provenance，便于与 Tripo 通道对比
            triangles = glb_triangles(data)
            if triangles is not None:
                info["triangles"] = triangles
        self.last_call_info.update(info)
        log.info(
            "[meshy] task=%s model=%s bytes=%s credits=%s",
            task_ids[-1],
            self.model,
            len(data),
            self.last_call_info.get("credits"),
        )
        return data

    # ── 账户 ──────────────────────────────────────────────────────────────

    def balance(self) -> dict:
        """查询剩余额度（不计费）。"""

        resp = self.client.request("GET", "/openapi/v1/balance")
        return resp if isinstance(resp, dict) else {"balance": resp}
