"""Smooth 2D character renderer with front / side / top views (pure stdlib).

Replaces the first-generation pixel-art renderer. Style target: soft cartoon
game art �?rounded silhouettes, uniform dark outline, flat fills with a light
belly/highlight and a ground shadow, big friendly eyes. Deterministic from the
asset palette + seed, and consistent across the three orthographic views so the
sheet is usable for production modelling.

    render_character_view(params, view, size) -> PNG bytes
    render_character_sheet(params, size, gap) -> PNG bytes   (front|side|top)
"""

import colorsys
import math

from artgen.character import (
    ROLE_KEYS,
    _rgb,
    _seed_int,
    _shade_triple,
    resolve_palette,
)
from artgen.png import encode_rgba
from artgen.raster import (
    Surface,
    capsule,
    ellipse,
    fill_polygon,
    offset_polygon,
)

DESIGN = 512.0  # design-space side length; all coordinates below live here
VIEWS = ("front", "side", "back")


# --------------------------------------------------------------------------
# colours
# --------------------------------------------------------------------------


def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _hue_shift(rgb, degrees):
    r, g, b = (c / 255.0 for c in rgb)
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + degrees / 360.0) % 1.0
    r, g, b = colorsys.hls_to_rgb(h, light, s)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def _colors(roles, hue=0.0):
    outline = _rgb(roles["outline"])
    base = _rgb(roles["base"])
    shadow = _rgb(roles["shadow"])
    accent = _rgb(roles["accent"])
    metal = _rgb(roles["metal"])
    if hue:
        base = _hue_shift(base, hue)
        accent = _hue_shift(accent, hue)
        shadow = _hue_shift(shadow, hue)
    # keep the outline genuinely dark for a readable cartoon silhouette
    if sum(outline) > 210:
        outline = _shade_triple(base, -0.72)
    return {
        "outline": outline,
        "base": base,
        "base_dark": _shade_triple(base, -0.22),
        "base_light": _shade_triple(base, 0.34),
        "belly": _mix(_shade_triple(base, 0.72), (255, 255, 255), 0.45),
        "muzzle": _mix(_rgb(roles["skin"]), (255, 255, 255), 0.35),
        "accent": accent,
        "accent_dark": _shade_triple(accent, -0.25),
        "hair": _rgb(roles["hair"]),
        "eyes": _rgb(roles["eyes"]),
        "dark": _shade_triple(outline, -0.15),
        "metal": metal,
        "horn": _mix(metal, (255, 248, 225), 0.55),
        "blush": _mix(accent, (255, 140, 165), 0.55),
        "white": (255, 255, 255),
        "shadow": shadow,
    }


def _ground(painter, cx, cy, rx, ry):
    painter.soft_ellipse(ellipse(cx, cy, rx, ry), painter.colors["dark"], alpha=48)


class Painter:
    def __init__(self, surface, colors, ox, oy, unit, flip=False):
        self.s = surface
        self.colors = colors
        self.ox = ox
        self.oy = oy
        self.u = unit
        self.flip = flip

    def _pts(self, points):
        ox, oy, u = self.ox, self.oy, self.u
        if self.flip:
            return [(ox + (DESIGN - x) * u, oy + y * u) for (x, y) in points]
        return [(ox + x * u, oy + y * u) for (x, y) in points]

    def shape(self, points, fill, outline=None, ow=6.0):
        pts = self._pts(points)
        if outline is not None and ow > 0:
            fill_polygon(self.s, self._pts(offset_polygon(points, ow)), outline)
        fill_polygon(self.s, pts, fill)

    def soft_ellipse(self, points, color, alpha=60):
        fill_polygon(self.s, self._pts(points), color, alpha=alpha)


# --------------------------------------------------------------------------
# shared body traits
# --------------------------------------------------------------------------


def _traits(seed):
    return {
        "pointy_ears": bool(seed & 1),
        "has_horn": bool((seed >> 1) & 1),
        "has_tail": bool((seed >> 2) & 1),
        "has_scarf": bool((seed >> 3) & 1),
        "has_weapon": bool((seed >> 4) & 1),
        "round_body": bool((seed >> 5) & 1),
    }


def _ear(painter, cx, cy, side, traits):
    c = painter.colors
    if traits["pointy_ears"]:
        tipx = cx + side * 34
        pts = [
            (cx - side * 34, cy + 26),
            (cx + side * 6, cy - 40),
            (tipx + side * 20, cy + 30),
        ]
        painter.shape(pts, c["base"], c["outline"], 5)
        painter.shape(
            [(cx - side * 12, cy + 16), (cx + side * 2, cy - 18), (cx + side * 20, cy + 18)],
            c["accent"],
            None,
        )
    else:
        painter.shape(ellipse(cx, cy, 44, 40, rot=side * 0.5), c["base"], c["outline"], 5)
        painter.shape(ellipse(cx + side * 4, cy + 4, 24, 20, rot=side * 0.5), c["accent"], None)


def _horn(painter, cx, cy, side, traits):
    if not traits["has_horn"]:
        return
    c = painter.colors
    painter.shape(capsule(cx, cy + 20, cx - side * 6, cy - 34, 13), c["horn"], c["outline"], 4)


def _arm(painter, x0, y0, x1, y1, r, side, traits):
    c = painter.colors
    painter.shape(capsule(x0, y0, x1, y1, r), c["base"], c["outline"], 5)
    painter.shape(ellipse(x1, y1, r * 1.05, r * 1.05), c["belly"], c["outline"], 4)


def _leg(painter, x0, y0, x1, y1, r, traits):
    c = painter.colors
    painter.shape(capsule(x0, y0, x1, y1, r), c["base_dark"], c["outline"], 5)
    painter.shape(ellipse(x1, y1 + r * 0.5, r * 1.3, r * 0.85), c["base"], c["outline"], 5)


def _scarf(painter, cx, cy, rx, ry, traits):
    if not traits["has_scarf"]:
        return
    c = painter.colors
    painter.shape(ellipse(cx, cy, rx, ry), c["accent"], c["outline"], 5)
    painter.shape(ellipse(cx, cy + 6, rx * 0.42, ry * 0.7), c["accent_dark"], None)


def _weapon(painter, x, y, angle, traits):
    if not traits["has_weapon"]:
        return
    c = painter.colors
    ux, uy = math.cos(angle), math.sin(angle)
    bx0, by0 = x - ux * 10, y - uy * 10
    bx1, by1 = x + ux * 120, y + uy * 120
    painter.shape(capsule(bx0, by0, bx1, by1, 11), c["metal"], c["outline"], 4)
    painter.shape(capsule(bx0, by0, bx1, by1, 4), _mix(c["metal"], (255, 255, 255), 0.5), None)
    gx, gy = x + ux * 6, y + uy * 6
    nx, ny = -uy, ux
    painter.shape(
        capsule(gx - nx * 26, gy - ny * 26, gx + nx * 26, gy + ny * 26, 9),
        c["accent"],
        c["outline"],
        4,
    )


# --------------------------------------------------------------------------
# views
# --------------------------------------------------------------------------


def _draw_front(p, traits):
    c = p.colors
    _ground(p, 256, 500, 150, 34)

    # tail peeking behind
    if traits["has_tail"]:
        p.shape(capsule(256, 400, 356, 356, 17), c["base"], c["outline"], 5)
        p.shape(ellipse(362, 352, 24, 24), c["accent"], c["outline"], 5)

    # legs
    _leg(p, 224, 430, 214, 498, 33, traits)
    _leg(p, 288, 430, 298, 498, 33, traits)

    # body
    body_ry = 104 if traits["round_body"] else 96
    p.shape(ellipse(256, 372, 112, body_ry), c["base"], c["outline"], 6)
    p.shape(ellipse(256, 392, 74, 68), c["belly"], None)
    _scarf(p, 256, 300, 94, 26, traits)

    # arms
    _arm(p, 176, 340, 138, 414, 28, -1, traits)
    _arm(p, 336, 340, 374, 414, 28, 1, traits)
    _weapon(p, 150, 300, -0.5, traits)

    # ears + horns behind head
    _ear(p, 150, 128, -1, traits)
    _ear(p, 362, 128, 1, traits)
    _horn(p, 196, 92, -1, traits)
    _horn(p, 316, 92, 1, traits)

    # head
    p.shape(ellipse(256, 196, 140, 134), c["base"], c["outline"], 6)
    # muzzle
    p.shape(ellipse(256, 258, 86, 62), c["muzzle"], c["outline"], 5)
    p.shape(ellipse(256, 228, 26, 18), c["dark"], None)
    # eyes
    for ex in (204, 308):
        p.shape(ellipse(ex, 182, 22, 29), c["dark"], None)
        p.shape(ellipse(ex - 7, 172, 8, 9), c["white"], None)
    # blush
    p.soft_ellipse(ellipse(168, 232, 30, 17), c["blush"], alpha=150)
    p.soft_ellipse(ellipse(344, 232, 30, 17), c["blush"], alpha=150)
    # smile
    for a, b in (((242, 268), (256, 276)), ((256, 276), (270, 268))):
        p.shape(capsule(a[0], a[1], b[0], b[1], 4), c["dark"], None)


def _draw_side(p, traits):
    c = p.colors
    _ground(p, 250, 500, 150, 34)

    if traits["has_tail"]:
        p.shape(capsule(178, 372, 108, 332, 16), c["base"], c["outline"], 5)
        p.shape(ellipse(100, 324, 24, 24), c["accent"], c["outline"], 5)

    _leg(p, 222, 430, 214, 500, 32, traits)
    _leg(p, 284, 430, 294, 500, 32, traits)

    body_ry = 104 if traits["round_body"] else 94
    p.shape(ellipse(248, 372, 100, body_ry), c["base"], c["outline"], 6)
    p.shape(ellipse(302, 398, 54, 56), c["belly"], None)
    _scarf(p, 252, 300, 84, 24, traits)

    _arm(p, 278, 338, 332, 406, 26, 1, traits)
    _weapon(p, 328, 300, 0.95, traits)

    _ear(p, 188, 96, -1, traits)
    _horn(p, 222, 92, 1, traits)

    # head + snout (snout kept modest and high so it reads in proportion)
    p.shape(ellipse(232, 196, 132, 126), c["base"], c["outline"], 6)
    p.shape(ellipse(334, 246, 54, 42), c["muzzle"], c["outline"], 5)
    # nose sits at the front-top of the snout
    p.shape(ellipse(380, 226, 16, 13), c["dark"], None)
    # mouth tucked just under the nose
    p.shape(capsule(362, 252, 374, 260, 3), c["dark"], None)
    # eye + highlight
    p.shape(ellipse(282, 176, 19, 26), c["dark"], None)
    p.shape(ellipse(276, 167, 7, 8), c["white"], None)
    p.soft_ellipse(ellipse(320, 238, 26, 15), c["blush"], alpha=150)


def _draw_back(p, traits):
    c = p.colors
    _ground(p, 256, 500, 150, 34)

    _leg(p, 224, 430, 214, 498, 33, traits)
    _leg(p, 288, 430, 298, 498, 33, traits)

    body_ry = 104 if traits["round_body"] else 96
    p.shape(ellipse(256, 372, 112, body_ry), c["base"], c["outline"], 6)
    p.soft_ellipse(ellipse(256, 372, 44, body_ry * 0.7), c["base_dark"], alpha=70)
    _scarf(p, 256, 300, 94, 26, traits)

    # tail hangs between the legs, so it must be drawn over the body
    if traits["has_tail"]:
        p.shape(capsule(256, 430, 256, 486, 15), c["base"], c["outline"], 5)
        p.shape(ellipse(256, 492, 20, 20), c["accent"], c["outline"], 5)

    _arm(p, 176, 340, 138, 414, 28, -1, traits)
    _arm(p, 336, 340, 374, 414, 28, 1, traits)

    # weapon carried on the back (diagonal)
    if traits["has_weapon"]:
        p.shape(capsule(208, 316, 326, 436, 10), c["metal"], c["outline"], 4)
        p.shape(capsule(208, 316, 326, 436, 3.5), _mix(c["metal"], (255, 255, 255), 0.5), None)
        p.shape(capsule(196, 348, 240, 358, 7), c["accent"], c["outline"], 3)
        p.shape(ellipse(202, 310, 12, 12), c["accent"], c["outline"], 4)

    _ear(p, 150, 128, -1, traits)
    _ear(p, 362, 128, 1, traits)
    _horn(p, 196, 92, -1, traits)
    _horn(p, 316, 92, 1, traits)

    # back of the head — no face
    p.shape(ellipse(256, 196, 140, 134), c["base"], c["outline"], 6)
    p.soft_ellipse(ellipse(256, 196, 106, 100), c["base_light"], alpha=70)


_DRAW = {"front": _draw_front, "side": _draw_side, "back": _draw_back}


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def _resolve(params):
    params = params or {}
    seed = _seed_int(params.get("seed") or 0)
    raw = params.get("palette")
    roles = resolve_palette(raw, seed)
    # flat colour lists (the backend's default palette) get a seed-driven hue
    # rotation so distinct prompts read as distinct characters; explicit
    # semantic-role palettes are honoured verbatim.
    hue = (((seed % 360) - 180) * 0.6) if not isinstance(raw, dict) else 0.0
    colors = _colors(roles, hue)
    traits = _traits(seed)
    extra = params.get("traits") or {}
    if isinstance(extra, dict):
        for key in ("has_weapon", "has_horn", "has_tail", "has_scarf"):
            if extra.get(key) is not None:
                traits[key] = bool(extra[key])
    return colors, traits


def _scale(size):
    return max(64, min(2048, int(size))) / DESIGN


def draw_view(surface, params, view, ox, oy, size):
    colors, traits = _resolve(params)
    unit = _scale(size)
    # the side view is authored facing right; mirror it to a left-side profile
    painter = Painter(surface, colors, ox, oy, unit, flip=(view == "side"))
    _DRAW[view if view in _DRAW else "front"](painter, traits)
    return int(size)


def render_character_view(params=None, view="front", size=512):
    size = max(64, min(2048, int(size)))
    surface = Surface(size, size)
    draw_view(surface, params, view, 0.0, 0.0, size)
    return encode_rgba(size, size, surface.to_rgba())


def render_character_sheet(params=None, size=512, gap=24):
    """Front | side | top sheet on a transparent background."""
    size = max(64, min(1024, int(size)))
    gap = max(0, int(gap))
    width = size * 3 + gap * 2
    surface = Surface(width, size)
    for index, view in enumerate(VIEWS):
        draw_view(surface, params, view, index * (size + gap), 0.0, size)
    return encode_rgba(width, size, surface.to_rgba())


# -- CreativeAsset -> params (mirrors artgen.character) ---------------------


def _palette_from_asset(asset):
    pixel = asset.get("pixel") or {}
    palette = pixel.get("palette") if isinstance(pixel, dict) else None
    if isinstance(palette, dict):
        if palette.get("semantic_roles"):
            return palette["semantic_roles"]
        if palette.get("colors"):
            return palette["colors"]
        if any(key in palette for key in ROLE_KEYS):
            return palette
    elif isinstance(palette, (list, tuple)) and palette:
        return list(palette)
    for owner in ("source", "character", "style"):
        block = asset.get(owner) or {}
        if isinstance(block, dict) and block.get("palette"):
            return block["palette"]
    return None


def _seed_from_asset(asset):
    identity = asset.get("identity") or {}
    source = asset.get("source") or {}
    if isinstance(source, dict) and source.get("seed") is not None:
        return source["seed"]
    return (
        identity.get("prompt") or identity.get("name") or asset.get("name") or asset.get("id") or 0
    )


def asset_params(asset):
    asset = asset or {}
    return {
        "palette": _palette_from_asset(asset),
        "seed": _seed_from_asset(asset),
        "traits": asset.get("character"),
    }


def render_asset_view(asset, view="front", size=512):
    return render_character_view(asset_params(asset), view=view, size=size)


def render_asset_sheet(asset, size=512, gap=24):
    return render_character_sheet(asset_params(asset), size=size, gap=gap)
