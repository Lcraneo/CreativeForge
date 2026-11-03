"""CG 视频算子：提示词/首帧图 → 云端视频 → MP4 写回 ``video`` 槽位。"""

from __future__ import annotations

from typing import Any, Optional

from . import base

__all__ = ["generate", "SLOT"]

SLOT = "video"


def generate(
    asset: dict,
    model,
    *,
    prompt: Optional[str] = None,
    image_url: Optional[str] = None,
    image: Any = None,
    duration: float | None = None,
    ratio: Optional[str] = None,
    seed: int | None = None,
    name: str = "",
) -> dict:
    """生成一段视频并写回资产扩展块，返回 ``video`` 槽位视图。"""

    target = base.resolve_asset(asset, required=True)
    if not prompt and not image_url and image is None:
        return base.record_failure(
            target, SLOT, str(getattr(model, "PROVIDER", "")), ValueError("需要 prompt 或 image_url 之一")
        )
    output_path = base.new_output_path(target, SLOT, "mp4", name=name or "video")
    return base.run_and_record(
        model,
        target,
        SLOT,
        output_path,
        extra={
            "model": str(getattr(model, "model", "")),
            "duration_s": float(duration) if duration else None,
        },
        prompt=prompt,
        image_url=image_url,
        image=image,
        duration=duration,
        ratio=ratio,
        seed=seed,
    )
