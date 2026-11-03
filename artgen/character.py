"""Deterministic character art renderer (pure stdlib).

The CreativeForge generation stack is a deterministic stand-in for a real
image model (see ``agent/generation/spec.py``). Upstream we only ever had a
*filename* string, never pixels, so the product UI had nothing to render and
the export archive carried flat colour blocks.

This module closes that gap: it turns a CreativeAsset (palette + seed +
character traits) into a real, recognisable pixel-art character sprite and
encodes it as a valid PNG. The output is:

    * fully deterministic — same asset -> byte-identical image,
    * dependency-free — standard library only,
    * a real raster image — 8-bit non-interlaced RGBA, 32px sprite grid
      upscaled with nearest-neighbour (crisp pixel-art look).

Swapping in a real diffusion/T2I model later only means returning different
bytes from :func:`render_character_png`; every caller keeps working.
"""

import hashlib

from artgen.png import encode_rgba

GRID = 32  # sprite is authored on a 32x32 pixel grid, then upscaled

ROLE_KEYS = (
    "outline",
    "shadow",
    "base",
    "highlight",
    "accent",
    "hair",
    "skin",
    "eyes",
    "metal",
)

DEFAULT_ROLES = {
    "outline": "#0b0e14",
    "shadow": "#232936",
    "base": "#4c6ef5",
    "highlight": "#8da2ff",
    "accent": "#ffb703",
    "hair": "#1b2230",
    "skin": "#e8b98a",
    "eyes": "#4cc2ff",
    "metal": "#94a3b8",
}

_NEIGHBOURS = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


# --------------------------------------------------------------------------
# colour helpers
# --------------------------------------------------------------------------


def _norm_hex(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    try:
        int(text, 16)
    except ValueError:
        return None
    return "#" + text.lower()


def _rgb(value):
    text = _norm_hex(value) or DEFAULT_ROLES["base"]
    text = text[1:]
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _rgba(value, alpha=255):
    r, g, b = _rgb(value)
    return (r, g, b, alpha)


def _luminance(value):
    r, g, b = _rgb(value)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _saturation(value):
    r, g, b = _rgb(value)
    return max(r, g, b) - min(r, g, b)


def _shade_triple(rgb, amount):
    """amount > 0 lightens, < 0 darkens (kept in sync with precon._seed.shade)."""
    r, g, b = rgb
    if amount >= 0:
        r = r + (255 - r) * amount
        g = g + (255 - g) * amount
        b = b + (255 - b) * amount
    else:
        r = r * (1 + amount)
        g = g * (1 + amount)
        b = b * (1 + amount)
    return (
        int(max(0, min(255, round(r)))),
        int(max(0, min(255, round(g)))),
        int(max(0, min(255, round(b)))),
    )


def _shade(value, amount, alpha=255):
    r, g, b = _shade_triple(_rgb(value), amount)
    return (r, g, b, alpha)


def _seed_int(seed):
    if isinstance(seed, bool):
        seed = int(seed)
    if isinstance(seed, int):
        return seed & 0xFFFFFFFF
    return int(hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:8], 16)


# --------------------------------------------------------------------------
# palette resolution: role dict OR flat colour list -> role dict
# --------------------------------------------------------------------------


def resolve_palette(palette, seed=0):
    """Best-effort mapping of any palette payload onto semantic roles."""
    roles = dict(DEFAULT_ROLES)

    if isinstance(palette, dict):
        semantic = palette.get("semantic_roles")
        if isinstance(semantic, dict):
            palette = {**palette, **semantic}
        for key in ROLE_KEYS:
            value = _norm_hex(palette.get(key))
            if value:
                roles[key] = value
        return roles

    colors = []
    if isinstance(palette, (list, tuple)):
        colors = [c for c in (_norm_hex(item) for item in palette) if c]

    if not colors:
        return roles

    ordered = sorted(colors, key=_luminance)
    outline = ordered[0]
    if _luminance(outline) > 90:
        outline = "#%02x%02x%02x" % _shade_triple(_rgb(outline), -0.55)
    highlight = ordered[-1]

    middles = ordered[1:-1] or ordered
    base = middles[len(middles) // 2]

    accent_pool = [c for c in colors if c not in (outline, highlight)] or colors
    accent = max(accent_pool, key=_saturation)
    if _saturation(accent) < 40:
        accent = highlight

    hair = ordered[1] if len(ordered) > 1 else roles["hair"]

    roles.update(
        outline=outline,
        base=base,
        highlight=highlight,
        accent=accent,
        hair=hair,
        shadow="#%02x%02x%02x" % _shade_triple(_rgb(base), -0.5),
        eyes=accent,
    )
    return roles


# --------------------------------------------------------------------------
# canvas
# --------------------------------------------------------------------------


class _Canvas:
    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.px = [(0, 0, 0, 0)] * (width * height)

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = color

    def get(self, x, y):
        return self.px[y * self.w + x]

    def fill_rect(self, x0, y0, x1, y1, color):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, color)

    def fill_ellipse(self, cx, cy, rx, ry, color):
        for y in range(cy - ry, cy + ry + 1):
            for x in range(cx - rx, cx + rx + 1):
                dx = (x - cx) / float(rx or 1)
                dy = (y - cy) / float(ry or 1)
                if dx * dx + dy * dy <= 1.0:
                    self.set(x, y, color)

    def outline(self, color):
        """Wrap every translucent pixel that touches an opaque one."""
        src = list(self.px)
        w, h = self.w, self.h

        def opaque(x, y):
            if 0 <= x < w and 0 <= y < h:
                return src[y * w + x][3] > 0
            return False

        for y in range(h):
            for x in range(w):
                if src[y * w + x][3] != 0:
                    continue
                if any(opaque(x + dx, y + dy) for dx, dy in _NEIGHBOURS):
                    self.px[y * w + x] = color

    def to_rgba(self):
        flat = bytearray()
        for r, g, b, a in self.px:
            flat += bytes((r, g, b, a))
        return bytes(flat)

    def upscale(self, factor):
        factor = max(1, int(factor))
        if factor == 1:
            return self.w, self.h, self.to_rgba()
        out_w, out_h = self.w * factor, self.h * factor
        flat = bytearray(out_w * out_h * 4)
        src = self.px
        for y in range(self.h):
            for x in range(self.w):
                r, g, b, a = src[y * self.w + x]
                if a == 0 and r == 0 and g == 0 and b == 0:
                    continue
                px = bytes((r, g, b, a))
                for oy in range(factor):
                    row = ((y * factor + oy) * out_w + x * factor) * 4
                    for ox in range(factor):
                        flat[row + ox * 4 : row + ox * 4 + 4] = px
        return out_w, out_h, bytes(flat)


# --------------------------------------------------------------------------
# sprite
# --------------------------------------------------------------------------


def _draw(canvas, roles, seed):
    outline = _rgba(roles["outline"])
    shadow = _rgba(roles["shadow"])
    base = _rgba(roles["base"])
    highlight = _rgba(roles["highlight"])
    accent = _rgba(roles["accent"])
    hair = _rgba(roles["hair"])
    skin = _rgba(roles["skin"])
    eyes = _rgba(roles["eyes"])
    metal = _rgba(roles["metal"])

    skin_shadow = _shade(roles["skin"], -0.2)
    base_shadow = _shade(roles["base"], -0.32)

    long_hair = bool(seed & 1)
    has_weapon = bool((seed >> 1) & 1)
    has_cape = bool((seed >> 2) & 1)

    # cape / cloak behind the body
    if has_cape:
        canvas.fill_rect(10, 14, 21, 25, shadow)
        canvas.fill_rect(11, 14, 20, 24, base_shadow)

    # legs + boots
    canvas.fill_rect(12, 22, 14, 27, base_shadow)
    canvas.fill_rect(17, 22, 19, 27, base_shadow)
    canvas.fill_rect(11, 27, 14, 29, outline)
    canvas.fill_rect(17, 27, 20, 29, outline)

    # torso + shoulders
    canvas.fill_rect(11, 13, 20, 22, base)
    canvas.fill_rect(11, 13, 20, 14, highlight)
    canvas.fill_rect(11, 21, 20, 22, accent)  # belt

    # arms + hands
    canvas.fill_rect(8, 14, 10, 21, base)
    canvas.fill_rect(21, 14, 23, 21, base)
    canvas.fill_rect(8, 20, 10, 22, skin)
    canvas.fill_rect(21, 20, 23, 22, skin)

    # neck + head
    canvas.fill_rect(14, 11, 17, 14, skin_shadow)
    canvas.fill_ellipse(16, 7, 4, 5, skin)

    # hair (cap + optional side strands)
    canvas.fill_ellipse(16, 5, 5, 4, hair)
    canvas.fill_rect(11, 4, 12, 9, hair)
    canvas.fill_rect(20, 4, 21, 9, hair)
    if long_hair:
        canvas.fill_rect(10, 5, 11, 15, hair)
        canvas.fill_rect(21, 5, 22, 15, hair)

    # face: eyes + mouth
    canvas.set(13, 8, eyes)
    canvas.set(14, 8, eyes)
    canvas.set(18, 8, eyes)
    canvas.set(19, 8, eyes)
    canvas.set(15, 10, skin_shadow)
    canvas.set(16, 10, skin_shadow)

    # weapon (blade + guard + hilt) on the free hand
    if has_weapon:
        canvas.fill_rect(24, 6, 24, 23, metal)
        canvas.fill_rect(25, 6, 25, 23, _shade(roles["metal"], 0.3))
        canvas.fill_rect(22, 14, 27, 15, accent)
        canvas.fill_rect(23, 23, 26, 25, hair)

    canvas.outline(outline)


def render_character_png(params=None, size=256):
    """Render a CreativeAsset-ish payload into character PNG bytes.

    ``params`` keys: ``palette`` (role dict or hex list), ``seed`` (int/str),
    ``traits`` (optional character dict).
    """
    params = params or {}
    seed = _seed_int(params.get("seed") or 0)
    roles = resolve_palette(params.get("palette"), seed)

    factor = max(1, int(size) // GRID)
    canvas = _Canvas(GRID, GRID)
    _draw(canvas, roles, seed)
    width, height, rgba = canvas.upscale(factor)
    return encode_rgba(width, height, rgba)


# --------------------------------------------------------------------------
# CreativeAsset -> render params
# --------------------------------------------------------------------------


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
        if isinstance(block, dict):
            candidate = block.get("palette")
            if candidate:
                return candidate
    return None


def _seed_from_asset(asset):
    identity = asset.get("identity") or {}
    source = asset.get("source") or {}
    if isinstance(source, dict) and source.get("seed") is not None:
        return source["seed"]
    return (
        identity.get("prompt") or identity.get("name") or asset.get("name") or asset.get("id") or 0
    )


def render_asset_png(asset, size=256):
    """CreativeAsset metadata -> character PNG bytes (deterministic)."""
    asset = asset or {}
    return render_character_png(
        {
            "palette": _palette_from_asset(asset),
            "seed": _seed_from_asset(asset),
            "traits": asset.get("character"),
        },
        size=size,
    )
