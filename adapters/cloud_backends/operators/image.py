"""图像算子：概念图 / T-pose → 云端图像 → PNG 写回 ``image`` 槽位。"""

from __future__ import annotations

import re
from typing import Optional

from . import base

__all__ = ["generate", "SLOT"]

SLOT = "image"


def _dimensions(size: str | None) -> tuple[int | None, int | None]:
    match = re.match(r"^\s*(\d+)\s*[xX*]\s*(\d+)\s*$", str(size or ""))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def generate(
    asset: dict,
    model,
    *,
    prompt: str = "",
    size: Optional[str] = None,
    seed: int | None = None,
    name: str = "",
) -> dict:
    """生成一张图并写回资产扩展块，返回 ``image`` 槽位视图。"""

    target = base.resolve_asset(asset, required=True)
    if not (prompt or "").strip():
        return base.record_failure(
            target, SLOT, str(getattr(model, "PROVIDER", "")), ValueError("需要非空 prompt")
        )
    output_path = base.new_output_path(target, SLOT, "png", name=name or "image")
    width, height = _dimensions(size)
    return base.run_and_record(
        model,
        target,
        SLOT,
        output_path,
        extra={
            "model": str(getattr(model, "model", "")),
            "width": width,
            "height": height,
            "seed": seed,
        },
        prompt=prompt,
        size=size,
        seed=seed,
    )
