"""3D 物体算子：图片/文本 → 云端 3D → GLB 写回 ``mesh`` 槽位。

编排权仍在 Supervisor：本算子只做单次能力调用，不做后端 fallback 决策；
路由层按 catalog 的 ``fallback`` 链决定是否换后端重试。
"""

from __future__ import annotations

from typing import Any, Optional

from . import base

__all__ = ["generate", "SLOT"]

SLOT = "mesh"


def generate(
    asset: dict,
    model,
    *,
    prompt: Optional[str] = None,
    image: Any = None,
    image_url: Optional[str] = None,
    seed: int | None = None,
    decimation_target: int | None = None,
    texture_size: int | None = None,
    name: str = "",
) -> dict:
    """生成 3D 资产并写回资产扩展块，返回 ``mesh`` 槽位视图。"""

    target = base.resolve_asset(asset, required=True)
    if not prompt and image is None and not image_url:
        return base.record_failure(
            target, SLOT, str(getattr(model, "PROVIDER", "")), ValueError("需要 prompt / image / image_url 之一")
        )
    ext = str(getattr(model, "OUTPUT_EXT", "glb") or "glb")
    output_path = base.new_output_path(target, SLOT, ext, name=name or "mesh")
    return base.run_and_record(
        model,
        target,
        SLOT,
        output_path,
        extra={
            "format": ext,
            "decimation_target": decimation_target,
            "texture_size": texture_size,
            "rigged": False,
        },
        prompt=prompt,
        image=image,
        image_url=image_url,
        seed=seed,
        decimation_target=decimation_target,
        texture_size=texture_size,
    )
