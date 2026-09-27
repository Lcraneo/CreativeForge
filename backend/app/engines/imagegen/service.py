"""Image generation service: one facade over the built-in core and every
configured provider, plus connectivity tests.

Model-call strategy (requirement 3): when no external provider is selected the
service falls back to the project's existing built-in generator, so behaviour
is unchanged for users who never configure an API.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.engines.imagegen.providers import (
    BUILTIN_PROVIDER,
    ProviderError,
    build_request,
    decode_image,
    extract_error,
    format_size,
    get_path,
    parse_image,
    sniff_mime,
)
from app.engines.imagegen.store import get_store

DEFAULT_TIMEOUT = 120.0
BUILTIN_MODEL = "artgen-2d"


@dataclass
class GenerateResult:
    data: bytes
    mime: str
    provider: str
    provider_label: str
    model: str
    source: str  # "api" | "builtin"
    size: str
    elapsed_ms: int
    meta: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_label": self.provider_label,
            "model": self.model,
            "source": self.source,
            "size": self.size,
            "mime": self.mime,
            "elapsed_ms": self.elapsed_ms,
        }


def _builtin_generate(prompt: str, size: str) -> GenerateResult:
    from artgen import render_character_view

    started = time.perf_counter()
    width = int(str(size).split("x")[0]) if "x" in str(size) else 1024
    width = max(64, min(1024, width))
    data = render_character_view({"seed": prompt, "palette": None}, "front", width)
    return GenerateResult(
        data=data,
        mime="image/png",
        provider=BUILTIN_PROVIDER,
        provider_label="项目内置管线",
        model=BUILTIN_MODEL,
        source="builtin",
        size=f"{width}x{width}",
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )


async def _baidu_token(client: httpx.AsyncClient, spec: dict[str, Any],
                       creds: dict[str, Any]) -> str:
    token_url = (spec.get("auth") or {}).get("token_url")
    response = await client.get(
        token_url,
        params={
            "grant_type": "client_credentials",
            "client_id": creds.get("api_key", ""),
            "client_secret": creds.get("secret_key", ""),
        },
    )
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise ProviderError(f"百度 access_token 获取失败: {extract_error(payload)}")
    return token


async def _poll(
    client: httpx.AsyncClient,
    spec: dict[str, Any],
    credentials: dict[str, Any],
    task_id: str,
    headers: dict[str, str],
    timeout: float,
) -> Any:
    cfg = spec.get("async") or {}
    endpoint = str(cfg.get("poll_endpoint", "")).format(task_id=task_id)
    deadline = time.time() + timeout
    interval = float(cfg.get("interval", 2.0))
    success = set(cfg.get("success") or ["SUCCEEDED"])
    failure = set(cfg.get("failure") or ["FAILED"])
    while time.time() < deadline:
        await _sleep(interval)
        poll_headers = {k: v for k, v in headers.items() if k.lower() == "authorization"}
        poll_headers.setdefault("Authorization", headers.get("Authorization", ""))
        response = await client.get(endpoint, headers=poll_headers)
        payload = response.json()
        status = str(get_path(payload, cfg.get("status_path", "output.task_status")) or "")
        if status in success:
            return payload
        if status in failure:
            raise ProviderError(f"厂商任务失败({status}): {extract_error(payload)}")
    raise ProviderError("厂商异步任务超时")


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


async def generate(
    prompt: str,
    provider_id: str | None = None,
    model: str | None = None,
    size: str | None = None,
    negative: str | None = None,
    seed: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> GenerateResult:
    store = get_store()
    selected = store.selected()
    pid = provider_id or selected.get("provider") or BUILTIN_PROVIDER

    if pid == BUILTIN_PROVIDER:
        return _builtin_generate(prompt, size or "1024x1024")

    spec = store.get_spec(pid)
    if spec is None:
        raise ProviderError(f"未知的图像服务商: {pid}")
    credentials = store.credentials(pid)
    missing = [f for f in (spec.get("credential_fields") or []) if not credentials.get(f)]
    if missing:
        raise ProviderError(f"服务商 {spec['label']} 缺少凭证: {', '.join(missing)}")

    resolved_model = model or selected.get("model") or spec.get("default_model") or ""
    resolved_size = size or spec.get("default_size") or "1024x1024"
    params = {
        "prompt": prompt,
        "negative": negative or "",
        "model": resolved_model,
        "size": resolved_size,
        "seed": seed,
    }

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        access_token = None
        if (spec.get("auth") or {}).get("mode") == "baidu_oauth":
            access_token = await _baidu_token(client, spec, credentials)

        method, url, headers, body = build_request(spec, params, credentials, access_token)
        response = await client.request(method, url, headers=headers, content=body)
        try:
            payload = response.json()
        except ValueError:
            raise ProviderError(f"HTTP {response.status_code}: {response.text[:200]}")

        if response.status_code >= 400:
            raise ProviderError(f"HTTP {response.status_code}: {extract_error(payload)}")

        if spec.get("async"):
            task_id = get_path(payload, (spec["async"]).get("submit_id_path"))
            if not task_id:
                raise ProviderError(f"未返回任务 id: {extract_error(payload)}")
            payload = await _poll(client, spec, credentials, str(task_id), headers, timeout)

        image_ref = parse_image(payload, spec)
        if not image_ref:
            raise ProviderError(f"响应中未找到图像: {extract_error(payload)}")

        data, mime = decode_image(image_ref)
        data = bytes(data)
        if not mime or mime == "application/octet-stream":
            mime = sniff_mime(data)

    return GenerateResult(
        data=data,
        mime=mime,
        provider=pid,
        provider_label=spec["label"],
        model=resolved_model,
        source="api",
        size=format_size(spec, resolved_size),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )


async def test_provider(
    provider_id: str, model: str | None = None, size: str | None = None
) -> dict[str, Any]:
    """Generate one tiny image to validate credentials + endpoint."""
    try:
        result = await generate(
            "a single red apple on a white background, simple product photo",
            provider_id=provider_id,
            model=model,
            size=size or "1024x1024",
            timeout=60.0,
        )
        return {
            "ok": True,
            "message": f"成功（{result.model}）",
            **result.describe(),
            "bytes": len(result.data),
        }
    except ProviderError as error:
        return {"ok": False, "message": str(error)}
    except Exception as error:  # network / parse
        return {"ok": False, "message": f"{type(error).__name__}: {error}"}
