"""音频算子：对白 / 音效 → 云端语音合成 → MP3 写回 ``audio`` 槽位。

一个 wrapper 双槽位：``kind=dialogue`` 念文本，``kind=sfx`` 用描述词出音效。
"""

from __future__ import annotations

from typing import Optional

from . import base

__all__ = ["generate", "SLOT"]

SLOT = "audio"


def generate(
    asset: dict,
    model,
    *,
    kind: str = "dialogue",
    text: str = "",
    prompt: str = "",
    voice: Optional[str] = None,
    speed: float | None = None,
    name: str = "",
) -> dict:
    """生成音频并写回资产扩展块，返回 ``audio`` 槽位视图。"""

    target = base.resolve_asset(asset, required=True)
    content = (text if kind == "dialogue" else prompt or text) or ""
    if kind not in ("dialogue", "sfx"):
        return base.record_failure(
            target, SLOT, str(getattr(model, "PROVIDER", "")), ValueError(f"未知音频槽位：{kind!r}")
        )
    if not content.strip():
        return base.record_failure(
            target, SLOT, str(getattr(model, "PROVIDER", "")), ValueError("音频内容不能为空")
        )
    output_path = base.new_output_path(target, SLOT, "mp3", name=name or kind)
    return base.run_and_record(
        model,
        target,
        SLOT,
        output_path,
        extra={"kind": kind},
        kind=kind,
        text=text,
        prompt=prompt,
        voice=voice,
        speed=speed,
    )
