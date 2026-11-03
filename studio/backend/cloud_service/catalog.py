"""云厂商目录：声明每个 provider 的能力映射、协议形态与凭据来源。

**单一事实源**：能力 → 后端映射、异步/同步协议、鉴权头形态、环境变量名，
以及是否复用模型广场已有凭据（``credential_ref``）都收敛在这里。
配置存储（``provider_store``）与后续生成路由只读这份声明，
不在各处硬编码厂商细节。

凭据安全：本文件只登记**环境变量名**，绝不包含任何密钥值。
"""

from __future__ import annotations

__all__ = [
    "PROVIDER_CATALOG",
    "PROVIDER_IDS",
    "provider_spec",
    "providers_for",
    "public_catalog",
]

# credential_ref 取值形态：``model_settings:<provider_id>:<field>``
# 表示复用模型广场已保存的连接凭据，避免用户重复填同一把 Key。
PROVIDER_CATALOG = {
    "bailian-tripo": {
        "label": "阿里云百炼 · Tripo 3D",
        "capabilities": ("gen_3d_object_cloud",),
        "slot": "mesh",
        "protocol": "async",
        "auth": "bearer",
        "env_keys": ("DASHSCOPE_API_KEY",),
        # 复用模型广场已保存的百炼 Key；WorkspaceId 无法复用，需单独配置
        "credential_ref": "model_settings:dashscope:api_key",
        "base_url": "https://{workspace_id}.cn-beijing.maas.aliyuncs.com",
        "model": "Tripo/Tripo-H3.1",
        "model_options": ("Tripo/Tripo-H3.1", "Tripo/Tripo-P1.0"),
        "extra_fields": ("workspace_id",),
        "region": "cn-beijing",
        "price_note": "H3.1 约 2.1 元/次；P1.0 约 3.5 元/次（以控制台为准）",
        "free_tier": "无免费额度，按次计费",
        "priority": 1,
        "fallback": "tripo",
        "notes": (
            "3D 主通道；仅华北2（北京）地域、必须该地域 Key，"
            "且 URL 必须带 WorkspaceId；输出 GLB（下载链接 2 小时有效）。"
        ),
    },
    "tripo": {
        "label": "Tripo3D 官方",
        "capabilities": ("gen_3d_object_cloud",),
        "slot": "mesh",
        "protocol": "async",
        "auth": "bearer",
        "env_keys": ("TRIPO_API_KEY",),
        "credential_ref": None,
        "base_url": "https://openapi.tripo3d.ai/v3",
        "model": "v3.1-20260211",
        "model_options": ("v3.1-20260211", "P1-20260311", "v2.5-20250123"),
        "extra_fields": (),
        "region": "",
        "price_note": "注册赠送 2000 credits，额度内零成本",
        "free_tier": "注册赠送 2000 credits",
        "priority": 2,
        "fallback": "meshy",
        "notes": "3D 备通道；支持本地图片上传（/files 换 file_token），输出 GLB。",
    },
    "meshy": {
        "label": "Meshy",
        "capabilities": ("gen_3d_object_cloud",),
        "slot": "mesh",
        "protocol": "async",
        "auth": "bearer",
        "env_keys": ("MESHY_API_KEY",),
        "credential_ref": None,
        "base_url": "https://api.meshy.ai",
        "model": "meshy-6",
        "model_options": ("meshy-6", "meshy-5"),
        "extra_fields": (),
        "region": "",
        "price_note": "免费 100 credits/月（约 3-5 次）",
        "free_tier": "每月赠送 100 credits；免费档 CC BY 4.0 需署名",
        "priority": 3,
        "fallback": "",
        "notes": "最终兜底；多格式（FBX / OBJ / USDZ / STL），仅前两条通道失败时启用。",
    },
    "ark": {
        "label": "火山方舟 ARK（Seedream / Seedance）",
        "capabilities": ("gen_image_cloud", "gen_cg_video_cloud"),
        "slot": "image",
        "protocol": "sync",
        "auth": "bearer",
        "env_keys": ("ARK_API_KEY",),
        # D3 决策：复用模型广场 volcengine 的密钥，用户只需配置一次
        "credential_ref": "model_settings:volcengine:api_key",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "",
        "free_tier": "以方舟控制台开通页为准",
        "priority": 1,
        "fallback": "",
        "notes": "图像走同步、视频走异步；模型 ID 以方舟开通页或推理接入点为准。",
    },
    "seed-audio": {
        "label": "Seed Audio",
        "capabilities": ("gen_audio_cloud",),
        "slot": "audio",
        "protocol": "sync",
        "auth": "bearer",
        "env_keys": ("SEED_AUDIO_API_KEY",),
        "credential_ref": None,
        "base_url": "https://openspeech.bytedance.com",
        "model": "seed-audio-1.0",
        "model_options": ("seed-audio-1.0",),
        "extra_fields": (),
        "region": "",
        "priority": 1,
        "fallback": "",
        "price_note": "以火山引擎语音控制台为准",
        "free_tier": "以厂商控制台为准",
        "notes": (
            "单 wrapper 双槽：dialogue（对白）与 sfx（音效）；端点 "
            "POST /api/v3/tts/create，参考音色需配置 SEED_AUDIO_SPEAKER_ID。"
        ),
    },
}

PROVIDER_IDS = tuple(PROVIDER_CATALOG)


def provider_spec(provider_id: str) -> dict | None:
    """取单个厂商声明；未登记返回 ``None``。"""

    return PROVIDER_CATALOG.get(str(provider_id or "").strip())


def providers_for(capability: str) -> list[str]:
    """按优先级返回支持指定能力的厂商 ID 列表（主后端在前）。"""

    matched = [
        pid for pid, spec in PROVIDER_CATALOG.items() if capability in spec.get("capabilities", ())
    ]
    return sorted(matched, key=lambda pid: PROVIDER_CATALOG[pid].get("priority", 99))


def public_catalog() -> list[dict]:
    """面向前端的厂商目录视图（只含环境变量名，不含任何密钥值）。"""

    return [
        {
            "id": pid,
            "label": spec["label"],
            "capabilities": list(spec["capabilities"]),
            "slot": spec["slot"],
            "protocol": spec["protocol"],
            "base_url": spec["base_url"],
            "model": spec["model"],
            "model_options": list(spec.get("model_options") or ()),
            "extra_fields": list(spec.get("extra_fields") or ()),
            "region": spec.get("region", ""),
            "price_note": spec.get("price_note", ""),
            "free_tier": spec["free_tier"],
            "priority": spec["priority"],
            "fallback": spec["fallback"],
            "env_keys": list(spec["env_keys"]),
            "credential_ref": spec["credential_ref"],
            "notes": spec["notes"],
        }
        for pid, spec in PROVIDER_CATALOG.items()
    ]
