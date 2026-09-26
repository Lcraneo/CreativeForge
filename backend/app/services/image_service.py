"""Character image service (2D redesign): serve smooth 2D artwork + 3 views.

The pipeline historically only carried a filename and the UI had nothing to
load. It now renders deterministic 2D cartoon artwork from a persisted asset
via the shared ``artgen`` renderer, in three orthographic views (front / side /
top) plus a combined sheet, so every product surface and the export archive
carry usable production art.
"""

from typing import Any

from artgen import VIEWS, render_asset_sheet, render_asset_view

IMAGE_PATH = "/api/v1/assets/{asset_id}/image.png"
SHEET_PATH = "/api/v1/assets/{asset_id}/views.png"

MIN_SIZE = 64
MAX_SIZE = 1024
DEFAULT_SIZE = 512
SHEET_MAX_SIZE = 768

VIEW_ALIASES = {
    "front": "front",
    "side": "side",
    "back": "back",
    "left": "side",
    "正视": "front",
    "正视图": "front",
    "正面图": "front",
    "侧视": "side",
    "侧视图": "side",
    "左侧面": "side",
    "左侧面图": "side",
    "左视图": "side",
    "后视": "back",
    "后视图": "back",
    "背视": "back",
    "背面图": "back",
}


def normalize_view(view: Any) -> str:
    if isinstance(view, str) and view.strip().lower() in VIEW_ALIASES:
        return VIEW_ALIASES[view.strip().lower()]
    return "front"


def clamp_size(size: Any, default: int = DEFAULT_SIZE, maximum: int = MAX_SIZE) -> int:
    try:
        value = int(size)
    except (TypeError, ValueError):
        value = default
    return max(MIN_SIZE, min(maximum, value))


def _url(path: str, **params: Any) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    return f"{path}?{query}" if query else path


def asset_view_url(asset_id: str, view: str = "front", size: int | None = None) -> str:
    return _url(
        IMAGE_PATH.format(asset_id=asset_id),
        view=normalize_view(view),
        size=clamp_size(size) if size else None,
    )


def asset_sheet_url(asset_id: str, size: int | None = None) -> str:
    return _url(
        SHEET_PATH.format(asset_id=asset_id),
        size=clamp_size(size, SHEET_MAX_SIZE, SHEET_MAX_SIZE) if size else None,
    )


# -- rendering (small per-process cache; deterministic output) ---------------

_CACHE: dict[tuple, bytes] = {}
_CACHE_LIMIT = 256


def render_asset_image(asset: dict[str, Any], size: int = DEFAULT_SIZE) -> bytes:
    """Backwards-compatible single image (front view)."""
    return render_asset_view_image(asset, view="front", size=size)


def render_asset_view_image(
    asset: dict[str, Any], view: str = "front", size: int = DEFAULT_SIZE
) -> bytes:
    view = normalize_view(view)
    size = clamp_size(size)
    key = (view, size, hash(str(asset)))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    payload = render_asset_view(asset or {}, view=view, size=size)
    _remember(key, payload)
    return payload


def render_asset_sheet_image(
    asset: dict[str, Any], size: int = SHEET_MAX_SIZE, gap: int = 24
) -> bytes:
    size = clamp_size(size, SHEET_MAX_SIZE, SHEET_MAX_SIZE)
    key = ("sheet", size, gap, hash(str(asset)))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    payload = render_asset_sheet(asset or {}, size=size, gap=gap)
    _remember(key, payload)
    return payload


def _remember(key: tuple, payload: bytes) -> None:
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.clear()
    _CACHE[key] = payload


def attach_image_url(asset: dict[str, Any], asset_id: str) -> dict[str, Any]:
    """Stamp loadable 2D image references onto ``content``."""
    content = asset.setdefault("content", {})
    if isinstance(content, dict):
        content["image_url"] = asset_view_url(asset_id, "front")
        content["image_mime"] = "image/png"
        content["image_style"] = "2d"
        content["views"] = {view: asset_view_url(asset_id, view) for view in VIEWS}
        content["views_sheet_url"] = asset_sheet_url(asset_id)
    return asset
