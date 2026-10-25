"""Tripo3D 官方 API（3D 备通道）。

相对百炼通道的两个差异值得注意：

- **支持本地上传**：``POST /files`` 把 PNG 换成 ``file_token``，无需公网 URL
- **支持 face_limit**：可请求目标面数（配合 ``smart_low_poly`` 时有 500–20000 的硬范围）

响应统一为 ``{"code": 0, "data": {...}}`` 信封；``code != 0`` 属于终态错误，
不重试。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from ..client import cloud_client
from .base import BaseCloudModel, glb_triangles

log = logging.getLogger("adapters.cloud_backends.tripo")

__all__ = ["TripoOfficialModel", "MODEL_OPTIONS", "DEFAULT_MODEL", "MODEL_ALIASES"]

MODEL_OPTIONS = ("v3.1-20260211", "P1-20260311", "v2.5-20250123")
DEFAULT_MODEL = "v3.1-20260211"

MODEL_ALIASES = {
    "tripo": DEFAULT_MODEL,
    "tripo-v3.1": "v3.1-20260211",
    "v3.1": "v3.1-20260211",
    "v3.0": "v3.0-20250812",
    "tripo-v3.0": "v3.0-20250812",
    "v2.5": "v2.5-20250123",
    "tripo-v2.5": "v2.5-20250123",
    "p1": "P1-20260311",
    "tripo-p1": "P1-20260311",
}

DONE_STATES = ("success", "succeeded", "finished", "completed")
FAILED_STATES = ("failed", "cancelled", "canceled", "banned", "expired", "unknown")

#: 产物 URL 字段随版本变化过，按实际出现顺序兜底
_MODEL_URL_KEYS = ("model_url", "pbr_model", "model", "base_model", "glb", "gltf")

#: ``smart_low_poly`` 开启时服务端接受的 face_limit 范围（超出即终态 400）
LOW_POLY_FACE_LIMIT_RANGE = (500, 20_000)


class TripoOfficialModel(BaseCloudModel):
    """Tripo 官方 v3 API 的 image-to-3D / text-to-3D。"""

    PROVIDER = "tripo"
    DEFAULT_MODEL = DEFAULT_MODEL
    OUTPUT_EXT = "glb"
    ENV_KEY = "TRIPO_API_KEY"
    DEFAULT_TASK_TIMEOUT = 1800.0

    def __init__(
        self,
        *,
        texture: bool = True,
        pbr: bool = True,
        texture_quality: str = "standard",
        geometry_quality: str = "standard",
        low_poly: bool = False,
        quad: bool = False,
        poll_interval: float = 3.0,
        **kwargs,
    ):
        super().__init__(poll_interval=poll_interval, **kwargs)
        self.model = MODEL_ALIASES.get(str(self.model).lower(), self.model)
        self.texture = texture
        self.pbr = pbr
        self.texture_quality = texture_quality
        self.geometry_quality = geometry_quality
        self.low_poly = low_poly
        self.quad = quad

    # ── 信封 ──────────────────────────────────────────────────────────────

    def _unwrap(self, resp: Any) -> dict:
        if not isinstance(resp, dict):
            raise cloud_client.CloudAPIError(
                f"响应不是对象：{type(resp).__name__}", provider=self.PROVIDER
            )
        code = resp.get("code")
        if code not in (None, 0):
            message = resp.get("message") or resp.get("msg") or resp
            suggestion = resp.get("suggestion")
            text = f"Tripo 错误 code={code}：{message}"
            if suggestion:
                text += f"（{suggestion}）"
            raise cloud_client.CloudAPIRequestError(text, provider=self.PROVIDER, payload=resp)
        data = resp.get("data")
        return data if isinstance(data, dict) else resp

    def _fetch_task(self, task_id: str) -> dict:
        return self._unwrap(self.client.request("GET", f"/tasks/{task_id}"))

    # ── 上传 ──────────────────────────────────────────────────────────────

    def _upload_png(self, png: bytes) -> str:
        data = self._unwrap(
            self.client.request(
                "POST",
                "/files",
                files={"file": ("input.png", png, "image/png")},
            )
        )
        token = data.get("file_token") or data.get("image_token") or data.get("token")
        if not token:
            raise cloud_client.CloudAPIError(
                f"上传成功但未返回 file_token：{data!r}", provider=self.PROVIDER
            )
        return str(token)

    @staticmethod
    def _to_png_bytes(image: Any) -> bytes | None:
        """把 PIL / numpy / bytes 统一为 PNG 字节；仅认识这三种输入。"""

        if image is None:
            return None
        if isinstance(image, (bytes, bytearray)):
            return bytes(image)
        try:
            from PIL import Image  # 项目已有依赖

            if isinstance(image, Image.Image):
                import io

                buffer = io.BytesIO()
                image.convert("RGBA").save(buffer, format="PNG")
                return buffer.getvalue()
            buffer = io.BytesIO()
            Image.fromarray(image).convert("RGBA").save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as error:  # noqa: BLE001 - 输入类型不可控
            raise ValueError(
                f"无法把 {type(image).__name__} 转成 PNG，请传 bytes 或 PIL.Image"
            ) from error

    # ── 载荷 ──────────────────────────────────────────────────────────────

    def _clamp_face_limit(self, value: int) -> int:
        value = int(value)
        if not self.low_poly:
            return value
        low, high = LOW_POLY_FACE_LIMIT_RANGE
        clamped = max(low, min(value, high))
        if clamped != value:
            log.warning(
                "[tripo] face_limit %s 收敛到 %s（smart_low_poly 允许 %s-%s）",
                value,
                clamped,
                low,
                high,
            )
        return clamped

    def _build_payload(
        self,
        *,
        prompt: Optional[str],
        negative_prompt: Optional[str],
        seed: int | None,
        decimation_target: int | None,
        provider_kwargs: dict,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "texture": self.texture,
            "pbr": self.pbr,
            "texture_quality": self.texture_quality,
            "geometry_quality": self.geometry_quality,
        }
        if self.low_poly:
            payload["smart_low_poly"] = True
        if self.quad:
            payload["quad"] = True
        if decimation_target:
            payload["face_limit"] = self._clamp_face_limit(decimation_target)
        if prompt:
            payload["prompt"] = prompt
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if seed is not None:
            # 服务端不保证同 seed 同结果，这里绝不本地伪造
            payload["model_seed"] = int(seed)
            payload["texture_seed"] = int(seed)
        payload.update(provider_kwargs)
        return payload

    @staticmethod
    def _extract_model_url(task: dict) -> str:
        output = task.get("output") or task.get("result") or {}
        for key in _MODEL_URL_KEYS:
            value = output.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
            if isinstance(value, dict) and isinstance(value.get("url"), str):
                return value["url"]
        raise cloud_client.CloudAPIError(
            f"任务成功但没有模型 URL：output={output!r}",
            provider="tripo",
            task_id=str(task.get("task_id") or ""),
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
        """生成 3D 资产并返回 GLB 字节（图片优先于文本）。"""

        png = self._to_png_bytes(image)
        if png is None and not image_url and not prompt:
            raise ValueError("需要 image / image_url / prompt 之一")
        if texture_size is not None:
            log.debug("[tripo] texture_size=%s 无对应参数，已忽略", texture_size)

        use_image = png is not None or bool(image_url)
        payload = self._build_payload(
            # 图片接口没有 prompt 字段，传了就是终态 400
            prompt=None if use_image else prompt,
            negative_prompt=None if use_image else negative_prompt,
            seed=seed,
            decimation_target=decimation_target,
            provider_kwargs=provider_kwargs,
        )
        cache_key = self._cache_key(
            payload=payload,
            image_sha256=cloud_client.bytes_hash(png),
            image_url=image_url or "",
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

        started = time.monotonic()
        if png is not None:
            payload["input"] = self._upload_png(png)
            endpoint = "/generation/image-to-model"
        elif image_url:
            payload["input"] = image_url
            endpoint = "/generation/image-to-model"
        else:
            endpoint = "/generation/text-to-model"

        created = self._unwrap(self.client.request("POST", endpoint, json_body=payload))
        task_id = str(created.get("task_id") or created.get("id") or "")
        if not task_id:
            raise cloud_client.CloudAPIError(
                f"{endpoint} 未返回 task_id：{created!r}", provider=self.PROVIDER
            )

        state = str(created.get("status", "")).lower()
        if state in DONE_STATES:
            task = created
        else:
            task = cloud_client.poll_task(
                lambda: self._fetch_task(task_id),
                task_id=task_id,
                timeout=self.task_timeout,
                poll_interval=self.poll_interval,
                done_states=DONE_STATES,
                failed_states=FAILED_STATES,
                status_key="status",
                provider=self.PROVIDER,
                sleep=self._sleep,
            )

        data = self._fetch_bytes(self._extract_model_url(task), cache_key)
        # GF 统一返回信息口径：provider/model/task_id/elapsed_sec/credits/
        # cached/cache_key/preview_url/triangles/bytes
        info: dict[str, Any] = {
            "provider": self.PROVIDER,
            "model": self.model,
            "task_id": task_id,
            "elapsed_sec": round(time.monotonic() - started, 2),
            "cached": False,
            "cache_key": cache_key,
            "bytes": len(data),
            "credits": task.get("credits_consumed", task.get("credits")),
            "preview_url": (task.get("output") or {}).get("rendered_image_url"),
        }
        if self.OUTPUT_EXT == "glb":
            triangles = glb_triangles(data)
            if triangles is not None:
                info["triangles"] = triangles
        self.last_call_info.update(info)
        log.info(
            "[tripo] task=%s model=%s %.1fs credits=%s triangles=%s bytes=%s",
            task_id,
            self.model,
            self.last_call_info.get("elapsed_sec") or 0.0,
            self.last_call_info.get("credits"),
            self.last_call_info.get("triangles"),
            len(data),
        )
        return data

    # ── 账户 ──────────────────────────────────────────────────────────────

    def balance(self) -> dict:
        """查询剩余额度（不计费）。"""

        return self._unwrap(self.client.request("GET", "/account/balance"))
