"""云管道基座：统一重试、错误分类、异步轮询、下载限额与响应缓存。

所有厂商 wrapper 只负责「构造请求 + 解析响应」，可靠性策略统一收敛在这里，
避免每个后端重复实现一遍重试与计费保护。

错误分类与契约 ``ERROR_CLASSES`` 一一对应：
``auth`` / ``quota`` / ``rate_limit`` / ``server`` / ``task_failed`` /
``task_timeout`` / ``invalid_request``。

依赖：只用项目已有的 ``httpx``（零新增依赖）。测试通过注入
``httpx.MockTransport`` 即可完全离线运行。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Callable, Iterable

import httpx

from .. import config

__all__ = [
    "RETRYABLE_STATUS",
    "CloudAPIError",
    "CloudAPIAuthError",
    "CloudAPIQuotaError",
    "CloudAPIRequestError",
    "CloudAPIServerError",
    "CloudAPIRateLimitError",
    "CloudTaskFailed",
    "CloudTaskTimeout",
    "classify_status",
    "CloudAPIClient",
    "poll_task",
    "request_hash",
    "bytes_hash",
    "ResponseCache",
    "APIErrorInfo",
]

RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class CloudAPIError(RuntimeError):
    """所有云调用失败的基类，``error_class`` 直接写入契约的失败槽位。"""

    error_class = "server"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        status: int | None = None,
        task_id: str = "",
        payload: Any = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.task_id = task_id
        self.payload = payload


class CloudAPIAuthError(CloudAPIError):
    error_class = "auth"


class CloudAPIQuotaError(CloudAPIError):
    error_class = "quota"


class CloudAPIRequestError(CloudAPIError):
    error_class = "invalid_request"


class CloudAPIServerError(CloudAPIError):
    error_class = "server"
    retryable = True


class CloudAPIRateLimitError(CloudAPIServerError):
    error_class = "rate_limit"


class CloudTaskFailed(CloudAPIError):
    error_class = "task_failed"


class CloudTaskTimeout(CloudAPIError):
    error_class = "task_timeout"


class APIErrorInfo(dict):
    """失败槽位所需的 ``{error_class, message}`` 轻量视图。"""


def classify_status(status: int, message: str = "") -> CloudAPIError:
    """把 HTTP 状态映射为异常实例（402 视为额度耗尽，与 Tripo 口径一致）。"""

    if status in (401, 403):
        return CloudAPIAuthError(message or "鉴权失败", status=status)
    if status == 402:
        return CloudAPIQuotaError(message or "额度不足", status=status)
    if status == 429:
        return CloudAPIRateLimitError(message or "请求过于频繁", status=status)
    if status in RETRYABLE_STATUS or status >= 500:
        return CloudAPIServerError(message or "服务端错误", status=status)
    return CloudAPIRequestError(message or "请求参数非法", status=status)


def _error_message(response: httpx.Response) -> str:
    """从响应体提取可读消息，最多保留 300 字，避免把整页 HTML 灌进日志。"""

    try:
        body = response.json()
    except ValueError:
        return (response.text or "").strip()[:300]
    if isinstance(body, dict):
        for key in ("message", "msg", "error", "detail", "code"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
            if isinstance(value, dict):
                inner = value.get("message") or value.get("code")
                if inner:
                    return str(inner)[:300]
    return str(body)[:300]


class CloudAPIClient:
    """单厂商的 HTTP 客户端：鉴权、重试、错误分类、下载限额。

    Args:
        base_url: API 根地址（可含已渲染的 ``workspace_id``）。
        api_key: Bearer 令牌。
        timeout: 单次请求超时（秒），不是任务超时。
        max_retries: 首次之外的重试次数，仅对可重试错误生效。
        backoff: 指数退避基数。
        transport: 注入 ``httpx`` 传输层（测试用 ``MockTransport``）。
        sleep: 注入休眠函数（测试用空实现避免真实等待）。
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        *,
        provider: str = "",
        timeout: int | None = None,
        max_retries: int | None = None,
        backoff: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self._api_key = api_key or ""
        self.provider = provider
        self.timeout = timeout if timeout is not None else config.request_timeout()
        self.max_retries = max_retries if max_retries is not None else config.max_retries()
        self.backoff = backoff
        self._sleep = sleep
        self._client = httpx.Client(
            timeout=self.timeout,
            transport=transport,
            follow_redirects=True,
        )

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # ── 请求 ──────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not self.base_url:
            raise CloudAPIError("未配置 base_url", provider=self.provider)
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if extra:
            headers.update(extra)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
        files: dict | None = None,
        headers: dict | None = None,
        expect_json: bool = True,
    ) -> Any:
        """发一次带重试的请求；返回解析后的 JSON（或文本）。"""

        url = self._url(path)
        attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = self._client.request(
                    method.upper(),
                    url,
                    json=json_body,
                    params=params,
                    files=files,
                    headers=self._headers(headers),
                )
            except httpx.TransportError as error:
                last_error = CloudAPIServerError(f"网络传输失败：{error}", provider=self.provider)
            else:
                if response.status_code < 400:
                    if not expect_json:
                        return response.text
                    try:
                        return response.json()
                    except ValueError as error:
                        raise CloudAPIError(
                            f"响应不是合法 JSON：{response.text[:200]!r}",
                            provider=self.provider,
                            status=response.status_code,
                        ) from error
                error = classify_status(response.status_code, _error_message(response))
                error.provider = self.provider
                last_error = error
                if not error.retryable:
                    raise error

            if attempt < attempts - 1:
                self._sleep(self.backoff * (2**attempt))

        raise last_error or CloudAPIError("请求失败", provider=self.provider)

    # ── 下载 ──────────────────────────────────────────────────────────────

    def download(self, url: str, *, max_bytes: int | None = None) -> bytes:
        """流式下载产物；超过上限立即中断，避免异常产物把磁盘写满。"""

        limit = max_bytes if max_bytes is not None else config.cache_max_bytes()
        attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                chunks: list[bytes] = []
                total = 0
                with self._client.stream("GET", url) as response:
                    if response.status_code >= 400:
                        error = classify_status(response.status_code, _error_message(response))
                        error.provider = self.provider
                        if not error.retryable:
                            raise error
                        last_error = error
                    else:
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > limit:
                                raise CloudAPIError(
                                    f"下载超过上限 {limit} 字节", provider=self.provider
                                )
                            chunks.append(chunk)
                        return b"".join(chunks)
            except httpx.TransportError as error:
                last_error = CloudAPIServerError(f"下载传输失败：{error}", provider=self.provider)
            except CloudAPIError:
                raise

            if attempt < attempts - 1:
                self._sleep(self.backoff * (2**attempt))

        raise last_error or CloudAPIError("下载失败", provider=self.provider)


# ── 异步任务轮询 ────────────────────────────────────────────────────────────


def poll_task(
    fetch: Callable[[], dict],
    *,
    task_id: str = "",
    timeout: float = 1800.0,
    poll_interval: float = 3.0,
    done_states: Iterable[str] = ("succeeded", "success", "completed"),
    failed_states: Iterable[str] = ("failed", "canceled", "cancelled", "expired"),
    status_key: str = "task_status",
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    provider: str = "",
) -> dict:
    """轮询直到终态；超时抛 ``CloudTaskTimeout``，失败态抛 ``CloudTaskFailed``。

    超时不代表服务端停止计费——错误里保留 ``task_id`` 便于人工续查。
    """

    done = {str(state).lower() for state in done_states}
    failed = {str(state).lower() for state in failed_states}
    deadline = now() + timeout

    while True:
        payload = fetch()
        if not isinstance(payload, dict):
            raise CloudAPIError(
                f"任务响应不是对象：{payload!r}", task_id=task_id, provider=provider
            )
        state = str(_dig(payload, status_key) or "").lower()

        if state in done:
            return payload
        if state in failed:
            raise CloudTaskFailed(
                f"任务 {task_id} 失败（{state}）：{_failure_message(payload) or state}",
                task_id=task_id,
                provider=provider,
                payload=payload,
            )
        if now() >= deadline:
            raise CloudTaskTimeout(
                f"任务 {task_id} 在 {timeout:.0f}s 内未完成（最后状态 {state or '未知'}）",
                task_id=task_id,
                provider=provider,
                payload=payload,
            )
        sleep(poll_interval)


def _dig(payload: dict, key: str) -> Any:
    """在 ``output`` / ``data`` / 顶层三处按顺序取字段（各厂商信封不同）。"""

    for container in (payload.get("output"), payload.get("data"), payload):
        if isinstance(container, dict) and key in container:
            return container[key]
    return None


def _failure_message(payload: dict) -> str:
    """提取失败原因：先查常规字段，再查结果列表（百炼把详情放在 ``results[0]``）。"""

    for key in ("message", "error", "msg"):
        value = _dig(payload, key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:300]

    for container in (payload.get("output"), payload.get("data"), payload):
        if not isinstance(container, dict):
            continue
        results = container.get("results")
        if not isinstance(results, list):
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            for key in ("message", "code"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:300]
    return ""


# ── 缓存 ────────────────────────────────────────────────────────────────────


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(payload: dict) -> str:
    """参数规范化哈希：同一请求不重复计费（契约 R9）。空值统一剔除。"""

    cleaned = {key: value for key, value in (payload or {}).items() if value is not None}
    return "sha256:" + hashlib.sha256(_canonical(cleaned).encode()).hexdigest()


def bytes_hash(data: bytes | None) -> str | None:
    if not data:
        return None
    return hashlib.sha256(data).hexdigest()


class ResponseCache:
    """按 ``request_hash`` 落盘的响应缓存，带 TTL 与总容量上限。

    目录结构：``<root>/<namespace>/<hash 前两位>/<hash>.<ext>``。
    超限时按 mtime 最旧优先清理，避免无限增长。
    """

    def __init__(
        self,
        root: str | None = None,
        namespace: str = "default",
        *,
        ttl_seconds: int | None = None,
        max_bytes: int | None = None,
    ):
        self.root = os.path.join(root or config.cache_dir(), namespace)
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else config.cache_ttl_seconds()
        self.max_bytes = max_bytes if max_bytes is not None else config.cache_max_bytes()

    def _path(self, key: str, ext: str) -> str:
        digest = key.split(":")[-1]
        return os.path.join(self.root, digest[:2], f"{digest}.{ext.lstrip('.')}")

    def get(self, key: str, ext: str = "bin") -> bytes | None:
        path = self._path(key, ext)
        if not os.path.isfile(path):
            return None
        try:
            if self.ttl_seconds > 0:
                age = time.time() - os.path.getmtime(path)
                if age > self.ttl_seconds:
                    os.remove(path)
                    return None
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return None

    def put(self, key: str, data: bytes, ext: str = "bin") -> str:
        path = self._path(key, ext)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
        self.evict()
        return path

    def evict(self) -> int:
        """清理过期与超额文件，返回删除数量。"""

        if not os.path.isdir(self.root):
            return 0
        entries: list[tuple[float, int, str]] = []
        now = time.time()
        removed = 0
        for directory, _, names in os.walk(self.root):
            for name in names:
                path = os.path.join(directory, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                if self.ttl_seconds > 0 and now - stat.st_mtime > self.ttl_seconds:
                    try:
                        os.remove(path)
                        removed += 1
                    except OSError:
                        pass
                    continue
                entries.append((stat.st_mtime, stat.st_size, path))

        total = sum(size for _, size, _ in entries)
        if total <= self.max_bytes:
            return removed
        for _, size, path in sorted(entries):
            if total <= self.max_bytes:
                break
            try:
                os.remove(path)
                total -= size
                removed += 1
            except OSError:
                pass
        return removed
