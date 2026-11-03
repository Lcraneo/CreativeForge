"""厂商 wrapper 工厂与连通性探测。

本模块是「厂商 ID → wrapper 实例」的唯一映射点：算子与路由都通过它取模型，
不各自 ``if provider == ...`` 分支。凭据由调用方注入（环境变量或加密存储），
本模块不读密钥文件、不依赖 studio 后端，保持子包自闭环。
"""

from __future__ import annotations

import time
from typing import Any

import httpx

__all__ = [
    "CAPABILITY_SLOTS",
    "PROVIDER_LABELS",
    "build_model",
    "probe",
]

#: 能力名 → 契约槽位（catalog 与 operators 共用同一口径）
CAPABILITY_SLOTS = {
    "gen_3d_object_cloud": "mesh",
    "gen_image_cloud": "image",
    "gen_cg_video_cloud": "video",
    "gen_audio_cloud": "audio",
}

PROVIDER_LABELS = {
    "bailian-tripo": "阿里云百炼 · Tripo 3D",
    "tripo": "Tripo3D 官方",
    "meshy": "Meshy",
    "ark": "火山方舟 ARK",
    "seed-audio": "Seed Audio",
}

#: 探测路径：优先用各厂商的账户/余额端点（不计费）
_PROBE_PATHS = {
    "tripo": "/account/balance",
    "meshy": "/openapi/v1/balance",
}


def _ark_class(capability: str):
    """ARK 一个厂商承载两个能力，按能力选 wrapper。"""

    from .models import seedance, seedream

    if capability in ("gen_cg_video_cloud", "video"):
        return seedance.SeedanceModel
    return seedream.SeedreamModel


def build_model(
    provider_id: str,
    *,
    capability: str = "",
    api_key: str = "",
    api_base: str = "",
    model: str = "",
    workspace_id: str = "",
    **options: Any,
):
    """按厂商 ID 构造 wrapper；未登记即抛 ``ValueError``。"""

    pid = str(provider_id or "").strip()

    if pid == "bailian-tripo":
        from .models.bailian_tripo import BailianTripoModel

        return BailianTripoModel(
            api_key=api_key,
            api_base=api_base,
            model=model,
            workspace_id=workspace_id,
            **options,
        )
    if pid == "tripo":
        from .models.tripo import TripoOfficialModel

        return TripoOfficialModel(api_key=api_key, api_base=api_base, model=model, **options)
    if pid == "meshy":
        from .models.meshy import MeshyModel

        return MeshyModel(api_key=api_key, api_base=api_base, model=model, **options)
    if pid == "ark":
        return _ark_class(capability)(api_key=api_key, api_base=api_base, model=model, **options)
    if pid == "seed-audio":
        from .models.seed_audio import SeedAudioModel

        return SeedAudioModel(api_key=api_key, api_base=api_base, model=model, **options)
    raise ValueError(f"未登记的云厂商：{provider_id!r}")


def probe(
    provider_id: str,
    *,
    api_key: str = "",
    api_base: str = "",
    timeout: float = 8.0,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """轻量连通性探测：只判断「端点可达 + 鉴权是否被拒」，不发起计费调用。

    返回 ``{"ok", "status", "detail", "latency_ms"}``：

    - 2xx / 404：端点可达（404 说明服务在线但路径不同，不视为失败）
    - 401 / 403：鉴权失败（Key 未生效）
    - 402：额度耗尽
    - 5xx / 传输错误：服务端或网络问题
    """

    base = (api_base or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "status": None, "detail": "未配置 base_url", "latency_ms": 0}

    path = _PROBE_PATHS.get(provider_id, "")
    url = f"{base}{path}" if path else base
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    started = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
    except httpx.TransportError as error:
        return {
            "ok": False,
            "status": None,
            "detail": f"网络不可达：{error}",
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    latency = int((time.monotonic() - started) * 1000)
    status = response.status_code
    if status in (401, 403):
        return {"ok": False, "status": status, "detail": "鉴权失败（Key 无效或无权限）", "latency_ms": latency}
    if status == 402:
        return {"ok": False, "status": status, "detail": "额度耗尽", "latency_ms": latency}
    if status >= 500:
        return {"ok": False, "status": status, "detail": f"服务端错误 HTTP {status}", "latency_ms": latency}
    return {"ok": True, "status": status, "detail": f"端点可达 HTTP {status}", "latency_ms": latency}
