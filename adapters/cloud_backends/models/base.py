"""云模型 wrapper 的公共骨架：惰性客户端、响应缓存、落盘与生命周期。

各 wrapper 只实现 ``infer()``（构造请求 + 解析响应），其余全部复用这里，
保证重试、缓存与错误分类只有一份实现。
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from .. import config
from ..client import cloud_client

__all__ = [
    "BaseCloudModel",
    "require_api_key",
    "image_to_data_uri",
    "glb_triangles",
    "merge_provider_kwargs",
]


def glb_triangles(data: bytes) -> int | None:
    """统计 GLB 的三角面数（GF ``glb_summary`` 口径），解析失败返回 ``None``。

    只读 JSON chunk 里每个 primitive 的 indices accessor count（mode 缺省或 4
    才是三角网格），不引入第三方解析器。
    """

    import json
    import struct

    try:
        if len(data) < 20 or data[:4] != b"glTF":
            return None
        chunk_length, chunk_type = struct.unpack_from("<I4s", data, 12)
        if chunk_type != b"JSON":
            return None
        gltf = json.loads(data[20 : 20 + chunk_length].decode("utf-8"))
        accessors = gltf.get("accessors") or []
        total = 0
        for mesh in gltf.get("meshes") or []:
            for primitive in mesh.get("primitives") or []:
                if primitive.get("mode", 4) != 4:
                    continue
                index = primitive.get("indices")
                if not isinstance(index, int) or index >= len(accessors):
                    return None
                count = accessors[index].get("count")
                if not isinstance(count, int):
                    return None
                total += count // 3
        return total or None
    except (ValueError, KeyError, struct.error, UnicodeDecodeError):
        return None


def png_bytes_of(image: Any) -> bytes | None:
    """把 PIL / numpy / bytes 统一为 PNG 字节；``None`` 原样返回，其余报错。"""

    if image is None:
        return None
    if isinstance(image, (bytes, bytearray)):
        return bytes(image)
    try:
        import io

        from PIL import Image  # 项目已有依赖

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


def merge_provider_kwargs(payload: dict, provider_kwargs: dict | None) -> dict:
    """透传厂商专属参数的保护性合并（GF seed_audio kwargs 保护模式）：

    ``None`` 不透传；payload 已有的核心字段不被意外覆盖；新增键原样追加。
    """

    for key, value in (provider_kwargs or {}).items():
        if value is None or key in payload:
            continue
        payload[key] = value
    return payload


def require_api_key(explicit: str, env_name: str, *, who: str) -> str:
    """取密钥；缺失时报出可操作的错误，而不是在请求时才 401。"""

    key = (explicit or os.environ.get(env_name, "")).strip()
    if not key:
        raise cloud_client.CloudAPIAuthError(
            f"{who} 缺少 API Key：请设置 {env_name} 或在云能力面板中配置",
            provider=who,
        )
    return key


def image_to_data_uri(png: bytes) -> str:
    """把 PNG 字节编码为 data URI（Meshy 单图接口接受该形式）。"""

    import base64

    encoded = base64.b64encode(png).decode()
    return f"data:image/png;base64,{encoded}"


class BaseCloudModel:
    """所有云后端 wrapper 的公共父类。"""

    PROVIDER = "base"
    DEFAULT_MODEL = ""
    OUTPUT_EXT = "glb"
    ENV_KEY = ""
    SIGNUP_HINT = ""
    #: 单次生成任务的等待上限（秒）。云端出模型可能数分钟，超时不退款。
    DEFAULT_TASK_TIMEOUT = 1800.0

    def __init__(
        self,
        *,
        api_key: str = "",
        api_base: str = "",
        model: str = "",
        task_timeout: float | None = None,
        poll_interval: float = 3.0,
        http_timeout: int | None = None,
        max_retries: int | None = None,
        backoff: float = 0.5,
        cache_dir: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        extra_headers: dict | None = None,
    ):
        self._api_key = api_key
        self.api_base = api_base
        self.model = model or self.DEFAULT_MODEL
        self.task_timeout = task_timeout if task_timeout is not None else self.DEFAULT_TASK_TIMEOUT
        self.poll_interval = poll_interval
        self._http_timeout = http_timeout
        self._max_retries = max_retries
        self._backoff = backoff
        self._transport = transport
        self._sleep = sleep
        self._extra_headers = dict(extra_headers or {})
        self._client: cloud_client.CloudAPIClient | None = None
        self._cache = cloud_client.ResponseCache(cache_dir or config.cache_dir(), self.PROVIDER)
        #: 最近一次真实调用的元信息，供算子写入 ``provenance``。
        self.last_call_info: dict[str, Any] = {}

    # ── 生命周期 ──────────────────────────────────────────────────────────

    @property
    def client(self) -> cloud_client.CloudAPIClient:
        """首次调用时才解析密钥并建连，构造阶段不需要凭据。"""

        if self._client is None:
            key = require_api_key(self._api_key, self.ENV_KEY, who=self.PROVIDER)
            self._client = cloud_client.CloudAPIClient(
                self.api_base,
                key,
                provider=self.PROVIDER,
                timeout=self._http_timeout,
                max_retries=self._max_retries,
                backoff=self._backoff,
                transport=self._transport,
                sleep=self._sleep,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    unload = close

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # ── 公共工具 ──────────────────────────────────────────────────────────

    def _headers(self, extra: dict | None = None) -> dict:
        headers = dict(self._extra_headers)
        headers.update(extra or {})
        return headers

    def _cache_key(self, **parts) -> str:
        return cloud_client.request_hash({"provider": self.PROVIDER, **parts})

    def _fetch_bytes(self, url: str, cache_key: str) -> bytes:
        """先查缓存，未命中再下载并回写（契约 R9：同请求不重复计费）。"""

        cached = self._cache.get(cache_key, ext=self.OUTPUT_EXT)
        if cached is not None:
            self.last_call_info.update({"cached": True, "cache_key": cache_key})
            return cached
        data = self.client.download(url)
        self._cache.put(cache_key, data, ext=self.OUTPUT_EXT)
        return data

    def infer_and_save(self, output_path: str, **kwargs) -> str:
        """``infer()`` 的落盘版本；输出路径由调用方决定，这里从不派生。"""

        if not output_path:
            raise ValueError("output_path 必填（产物落点由调用方决定）")
        data = self.infer(**kwargs)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return str(out)

    def infer(self, **kwargs) -> bytes:  # pragma: no cover - 由子类实现
        raise NotImplementedError
