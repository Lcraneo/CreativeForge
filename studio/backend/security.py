"""Studio security middleware: auth, security headers, rate limiting.

全部读取环境变量，缺省时保持本地开发的开放行为：

- ``STUDIO_AUTH_TOKEN``   设置后 ``/api`` 与 ``/ws`` 全部要求令牌。三个通道任选其一：
                          ``Authorization: Bearer <token>``、cookie ``studio_token``
                          （让 ``<img src="/api/...">`` 与 WebSocket 握手自动携带）、
                          或查询参数 ``?token=``（WS 客户端兜底）。未设置 = 关闭鉴权。
- ``STUDIO_CORS_ORIGINS`` 逗号分隔白名单，默认仅本机 5173/8600。
- ``STUDIO_RATE_LIMIT``   每分钟每 IP 的写请求（POST/PUT/PATCH/DELETE）上限，
                          默认 120，0 = 关闭。

中间件是纯 ASGI 实现：BaseHTTPMiddleware 不处理 websocket scope，
鉴权必须同时覆盖 ``/ws`` 握手。
"""

import hmac
import json
import os
import time
from collections import deque
from urllib.parse import unquote, urlsplit

COOKIE_NAME = "studio_token"

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://localhost:8600,"
    "http://127.0.0.1:8600"
)


def allowed_origins() -> list[str]:
    raw = os.environ.get("STUDIO_CORS_ORIGINS", "").strip() or DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def auth_token() -> str:
    return os.environ.get("STUDIO_AUTH_TOKEN", "").strip()


def rate_limit() -> int:
    try:
        return int(os.environ.get("STUDIO_RATE_LIMIT", "120"))
    except ValueError:
        return 120


def _header_dict(scope) -> dict[bytes, bytes]:
    return {key: value for key, value in scope.get("headers", [])}


def _provided_token(scope) -> str:
    headers = _header_dict(scope)
    authorization = headers.get(b"authorization", b"").decode("latin-1")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    for part in headers.get(b"cookie", b"").decode("latin-1").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value.strip()

    for pair in scope.get("query_string", b"").decode("latin-1").split("&"):
        name, _, value = pair.partition("=")
        if name == "token":
            return unquote(value).strip()
    return ""


class AuthMiddleware:
    """Bearer/cookie/query 令牌校验，覆盖 http 与 websocket 两个 scope。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        token = auth_token()
        path = scope.get("path", "")
        protected = path.startswith("/api") or path.startswith("/ws")
        if scope["type"] == "http" and scope.get("method") == "OPTIONS":
            protected = False  # CORS 预检不携带自定义头

        if not token or not protected:
            return await self.app(scope, receive, send)

        provided = _provided_token(scope)
        if provided and hmac.compare_digest(provided, token):
            return await self.app(scope, receive, send)

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
            return

        body = json.dumps({"detail": "unauthorized"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    """为所有 HTTP 响应附加安全响应头；HSTS 仅在 https 请求上发送。"""

    CSP = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "font-src 'self'; "
        "connect-src 'self' ws://localhost:* ws://127.0.0.1:*; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    HEADERS = [
        ("Content-Security-Policy", CSP),
        ("X-Frame-Options", "DENY"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
        ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
        ("Cross-Origin-Opener-Policy", "same-origin"),
    ]

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name for name, _ in headers}
                for name, value in self.HEADERS:
                    if name.lower().encode() not in existing:
                        headers.append((name.lower().encode(), value.encode()))
                scheme = scope.get("scheme", "http")
                forwarded = _header_dict(scope).get(b"x-forwarded-proto", b"").decode()
                if scheme == "https" or forwarded == "https":
                    headers.append(
                        (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    """按 IP 的滑动窗口限流，只针对 /api 下的写请求；进程内存态，单用户工具够用。"""

    MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, app):
        self.app = app
        self._hits: dict[str, deque] = {}

    async def __call__(self, scope, receive, send):
        limit = rate_limit()
        if (
            scope["type"] == "http"
            and limit > 0
            and scope.get("method") in self.MUTATING_METHODS
            and scope.get("path", "").startswith("/api")
        ):
            client = scope.get("client")
            ip = client[0] if client else "unknown"
            now = time.time()
            hits = self._hits.setdefault(ip, deque())
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= limit:
                body = json.dumps({"detail": "rate limit exceeded"}).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"retry-after", b"30"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
            hits.append(now)

        await self.app(scope, receive, send)


def origin_allowed(origin: str | None, host_header: str | None) -> bool:
    """浏览器一定带 Origin；同源（与 Host 一致）放行，其余按白名单。"""
    if origin is None:
        return True  # 非浏览器客户端
    if origin in allowed_origins():
        return True
    if not host_header:
        return False
    return urlsplit(origin).netloc == host_header
