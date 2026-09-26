"""artgen — deterministic, dependency-free character art for CreativeForge.

Second generation: smooth 2D cartoon artwork (anti-aliased vector style) with
front / side / top orthographic views, produced from a CreativeAsset's palette
and seed. Standard library only, fully deterministic.

The legacy pixel renderer remains importable as ``artgen.character`` but the
public helpers below now emit the 2D style.
"""

from artgen.character import resolve_palette
from artgen.character2d import (
    VIEWS,
    asset_params,
    render_asset_sheet,
    render_asset_view,
    render_character_sheet,
    render_character_view,
)
from artgen.character2d import render_asset_view as render_asset_png
from artgen.character2d import render_character_view as render_character_png
from artgen.png import PNG_MAGIC, encode_rgba

__all__ = [
    "VIEWS",
    "render_character_png",
    "render_character_view",
    "render_character_sheet",
    "render_asset_png",
    "render_asset_view",
    "render_asset_sheet",
    "asset_params",
    "resolve_palette",
    "encode_rgba",
    "PNG_MAGIC",
]
