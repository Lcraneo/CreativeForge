"""Image-generation provider registry + wire adapters.

Seven hosted vendors are pre-registered (a mix of OpenAI-compatible
``/images/generations`` endpoints, DashScope's async task API, Baidu's OAuth
token flow and Tencent's TC3-HMAC-SHA256 signing). Everything is declarative:

    request body template  ->  auth strategy  ->  response image path(s)

so a *custom* provider can be expressed with the same fields. Request building
and response parsing are pure functions (unit-testable without network).

NOTE: vendor endpoints / model ids / parameter names drift over time. The
defaults below are best-effort starting points — verify against each vendor's
current documentation and adjust the provider config (or add a custom one).
"""

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

BUILTIN_PROVIDER = "builtin"

# --------------------------------------------------------------------------
# provider specifications
# --------------------------------------------------------------------------

PROVIDERS: dict[str, dict[str, Any]] = {
    "volcengine": {
        "id": "volcengine",
        "label": "字节 · 火山方舟（Seedream / 即梦）",
        "vendor": "字节跳动",
        "models": ["doubao-seedream-3-0-t2i-250415", "doubao-seedream-4-0-250828"],
        "default_model": "doubao-seedream-3-0-t2i-250415",
        "default_size": "1024x1024",
        "size_format": "x",
        "endpoint": "https://ark.cn-beijing.volces.com/api/v3/images/generations",
        "method": "POST",
        "auth": {"mode": "bearer"},
        "credential_fields": ["api_key"],
        "body": {
            "model": "{model}",
            "prompt": "{prompt}",
            "size": "{size}",
            "response_format": "url",
            "watermark": False,
        },
        "image_paths": ["data.0.b64_json", "data.0.url"],
        "notes": "OpenAI 兼容 + Bearer。response_format=url 时下载 URL。",
    },
    "dashscope": {
        "id": "dashscope",
        "label": "阿里 · 百炼 DashScope（通义万相 WanX）",
        "vendor": "阿里云",
        "models": [
            "wanx2.1-t2i-turbo",
            "wanx2.1-t2i-plus",
            "wanx-v1",
        ],
        "default_model": "wanx2.1-t2i-turbo",
        "default_size": "1024x1024",
        "size_format": "*",
        "endpoint": (
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/"
            "text2image/image-synthesis"
        ),
        "method": "POST",
        "auth": {"mode": "bearer"},
        "credential_fields": ["api_key"],
        "body": {
            "model": "{model}",
            "input": {"prompt": "{prompt}", "negative_prompt": "{negative}"},
            "parameters": {"size": "{size}", "n": 1},
        },
        "image_paths": ["output.results.0.url"],
        "async": {
            "submit_id_path": "output.task_id",
            "poll_endpoint": "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
            "status_path": "output.task_status",
            "success": ["SUCCEEDED"],
            "failure": ["FAILED", "CANCELED", "UNKNOWN"],
            "interval": 2.0,
        },
        "extra_headers": {"X-DashScope-Async": "enable"},
        "notes": "异步任务：提交后轮询 /api/v1/tasks/{id}。尺寸用 * 分隔。",
    },
    "qianfan": {
        "id": "qianfan",
        "label": "百度 · 千帆（ERNIE-ViLG 文心一格）",
        "vendor": "百度智能云",
        "models": ["ernie-vilg-v3", "sd_xl"],
        "default_model": "ernie-vilg-v3",
        "default_size": "1024x1024",
        "size_format": "x",
        "endpoint": (
            "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/"
            "wenxinworkshop/text2image/{model}"
        ),
        "method": "POST",
        "auth": {
            "mode": "baidu_oauth",
            "token_url": "https://aip.baidubce.com/oauth/2.0/token",
        },
        "credential_fields": ["api_key", "secret_key"],
        "body": {"prompt": "{prompt}", "size": "{size}", "n": 1},
        "image_paths": ["data.0.b64_image", "data.0.url"],
        "query_param": "access_token",
        "notes": "先取 access_token（api_key=AK, secret_key=SK），access_token 走查询串。",
    },
    "hunyuan": {
        "id": "hunyuan",
        "label": "腾讯云 · 混元图像（HY-Image）",
        "vendor": "腾讯云",
        "models": ["hunyuan"],
        "default_model": "hunyuan",
        "default_size": "1024x1024",
        "size_format": ":",
        "endpoint": "https://hunyuan.tencentcloudapi.com/",
        "method": "POST",
        "auth": {
            "mode": "tencent_tc3",
            "service": "hunyuan",
            "host": "hunyuan.tencentcloudapi.com",
            "action": "TextToImage",
            "version": "2023-09-01",
            "region": "ap-guangzhou",
        },
        "credential_fields": ["secret_id", "secret_key"],
        "body": {"Prompt": "{prompt}", "Resolution": "{size}"},
        "image_paths": ["Response.ResultImage", "Response.ResultImageUrl"],
        "notes": "TC3-HMAC-SHA256 签名。ResultImage 为 base64。",
    },
    "zhipu": {
        "id": "zhipu",
        "label": "智谱 AI · GLM-Image / CogView",
        "vendor": "智谱",
        "models": ["cogview-4", "cogview-3-flash", "glm-image"],
        "default_model": "cogview-4",
        "default_size": "1024x1024",
        "size_format": "x",
        "endpoint": "https://open.bigmodel.cn/api/paas/v4/images/generations",
        "method": "POST",
        "auth": {"mode": "bearer"},
        "credential_fields": ["api_key"],
        "body": {"model": "{model}", "prompt": "{prompt}", "size": "{size}"},
        "image_paths": ["data.0.url", "data.0.b64_json"],
        "notes": "OpenAI 风格 Bearer。",
    },
    "kuaishou": {
        "id": "kuaishou",
        "label": "快手 · 可图 Kolors",
        "vendor": "快手",
        "models": ["Kwai-Kolors/Kolors", "kolors"],
        "default_model": "Kwai-Kolors/Kolors",
        "default_size": "1024x1024",
        "size_format": "x",
        "endpoint": "https://api.siliconflow.cn/v1/images/generations",
        "method": "POST",
        "auth": {"mode": "bearer"},
        "credential_fields": ["api_key"],
        "body": {
            "model": "{model}",
            "prompt": "{prompt}",
            "image_size": "{size}",
            "batch_size": 1,
        },
        "image_paths": ["data.0.url", "images.0.url", "data.0.b64_json"],
        "notes": "默认走硅基流动托管；快手官方开放平台需签名，请改用自定义服务商。",
    },
    "meitu": {
        "id": "meitu",
        "label": "美图 · MiracleVision",
        "vendor": "美图",
        "models": ["miraclevision"],
        "default_model": "miraclevision",
        "default_size": "1024x1024",
        "size_format": "x",
        "endpoint": "https://openapi.mtlab.meitu.com/v1/t2i",
        "method": "POST",
        "auth": {"mode": "header", "headers": {"X-App-Id": "{app_key}"}},
        "credential_fields": ["api_key", "app_key"],
        "body": {"prompt": "{prompt}", "width": "{width}", "height": "{height}"},
        "image_paths": ["data.0.url", "result.url", "media_info_list.0.media_url"],
        "notes": "开放平台接口/签名随版本变化，请按官方文档调整；可改用自定义服务商。",
    },
}

PROVIDER_ORDER = [
    "volcengine", "dashscope", "qianfan", "hunyuan", "zhipu", "kuaishou", "meitu",
]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def get_path(payload: Any, path: str) -> Any:
    """'data.0.url' -> payload['data'][0]['url']; None if absent."""
    node = payload
    for part in str(path).split("."):
        if node is None:
            return None
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


def _subst(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {k: _subst(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_subst(v, ctx) for v in value]
    if isinstance(value, str):
        return re.sub(
            r"\{(\w+)\}",
            lambda m: str(ctx.get(m.group(1), "") if ctx.get(m.group(1)) is not None else ""),
            value,
        )
    return value


def _parse_size(size: str) -> tuple[int, int]:
    parts = re.split(r"[xX*:]", str(size or "1024x1024"))
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else int(parts[0])
    except (ValueError, IndexError):
        return 1024, 1024


def format_size(spec: dict[str, Any], size: str) -> str:
    width, height = _parse_size(size)
    sep = spec.get("size_format", "x")
    return f"{width}{sep}{height}"


def provider_public(spec: dict[str, Any], credentials: dict[str, Any] | None = None,
                    custom: bool = False) -> dict[str, Any]:
    creds = credentials or {}
    key = creds.get("api_key") or creds.get("secret_key") or ""
    hint = f"{key[:3]}****{key[-4:]}" if len(str(key)) > 8 else ("****" if key else "")
    return {
        "id": spec["id"],
        "label": spec["label"],
        "vendor": spec.get("vendor", "自定义"),
        "models": list(spec.get("models") or []),
        "default_model": spec.get("default_model") or "",
        "default_size": spec.get("default_size", "1024x1024"),
        "auth_mode": (spec.get("auth") or {}).get("mode", "bearer"),
        "credential_fields": list(spec.get("credential_fields") or ["api_key"]),
        "notes": spec.get("notes", ""),
        "builtin": spec["id"] == BUILTIN_PROVIDER,
        "custom": custom,
        "configured": all(creds.get(f) for f in (spec.get("credential_fields") or ["api_key"])),
        "has_key": bool(key),
        "key_hint": hint,
    }


# --------------------------------------------------------------------------
# auth / signing
# --------------------------------------------------------------------------

def _tencent_tc3_headers(
    secret_id: str, secret_key: str, auth: dict[str, Any],
    payload: bytes, timestamp: int | None = None,
) -> dict[str, str]:
    service = auth.get("service", "hunyuan")
    host = auth["host"]
    algorithm = "TC3-HMAC-SHA256"
    ts = int(timestamp or time.time())
    date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    content_type = "application/json; charset=utf-8"

    canonical_headers = f"content-type:{content_type}\nhost:{host}\n"
    signed_headers = "content-type;host"
    hashed_payload = hashlib.sha256(payload).hexdigest()
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, hashed_payload]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        [
            algorithm,
            str(ts),
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = _sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _sign(secret_date, service)
    secret_signing = _sign(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": content_type,
        "Host": host,
        "X-TC-Action": auth["action"],
        "X-TC-Version": auth["version"],
        "X-TC-Timestamp": str(ts),
        "X-TC-Region": auth.get("region", ""),
    }


class ProviderError(Exception):
    """Raised when a provider request/response cannot produce an image."""


def build_request(
    spec: dict[str, Any],
    params: dict[str, Any],
    credentials: dict[str, Any],
    access_token: str | None = None,
) -> tuple[str, str, dict[str, str], bytes | None]:
    """(method, url, headers, body) for one image request — pure function."""
    ctx = dict(params)
    ctx["negative"] = params.get("negative") or ""
    ctx["model"] = params.get("model") or spec.get("default_model") or ""
    ctx["size"] = format_size(spec, params.get("size") or spec.get("default_size"))
    width, height = _parse_size(params.get("size") or spec.get("default_size", "1024x1024"))
    ctx["width"], ctx["height"] = width, height
    for field in spec.get("credential_fields") or []:
        ctx[field] = credentials.get(field, "")

    url = spec["endpoint"]
    if "{" in url:
        url = re.sub(r"\{(\w+)\}", lambda m: str(ctx.get(m.group(1), "")), url)

    body = _subst(spec.get("body") or {}, ctx)
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    headers.update(spec.get("extra_headers") or {})

    auth = spec.get("auth") or {}
    mode = auth.get("mode", "bearer")
    if mode == "bearer":
        headers["Authorization"] = f"Bearer {credentials.get('api_key', '')}"
    elif mode == "header":
        for key, value in (auth.get("headers") or {}).items():
            headers[key] = re.sub(
                r"\{(\w+)\}", lambda m: str(ctx.get(m.group(1), "")), value
            )
    elif mode == "baidu_oauth":
        token = access_token or ""
        joiner = "&" if "?" in url else "?"
        query = spec.get("query_param", "access_token")
        if token:
            url = f"{url}{joiner}{query}={token}"
    elif mode == "tencent_tc3":
        headers.update(
            _tencent_tc3_headers(
                credentials.get("secret_id", ""),
                credentials.get("secret_key", ""),
                auth,
                body_bytes,
                timestamp=params.get("_timestamp"),
            )
        )
    return spec.get("method", "POST"), url, headers, body_bytes


def parse_image(payload: Any, spec: dict[str, Any]) -> str | None:
    """Return an image url / base64 string from a response payload."""
    for path in spec.get("image_paths") or []:
        value = get_path(payload, path)
        if isinstance(value, str) and value:
            return value
    return None


def extract_error(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("error", "message", "Message", "msg", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict) and value.get("message"):
                return str(value["message"])
        if payload.get("Response") and payload["Response"].get("Error"):
            err = payload["Response"]["Error"]
            return str(err.get("Message") or err)
    return str(payload)[:300]


def decode_image(value: str) -> tuple[bytes, str]:
    """base64 / data-uri / http url -> (bytes, mime)."""
    if value.startswith("data:"):
        header, _, data = value.partition(",")
        mime = header[5:].split(";")[0] or "image/png"
        return base64.b64decode(data), mime
    if value.startswith("http://") or value.startswith("https://"):
        return _download(value)
    padded = value + "=" * (-len(value) % 4)
    return base64.b64decode(padded), "image/png"


def _download(url: str) -> tuple[bytes, str]:
    import httpx

    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        mime = response.headers.get("Content-Type", "image/png").split(";")[0]
        return response.content, mime or "image/png"


def sniff_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"
