"""Source-driven 2D animation: animate the *actual* source image.

Instead of re-drawing a different character (which broke content/style/
composition consistency), this perturbs the source artwork itself: the subject
is segmented out and transformed (bob / sway / squash / rotate / lunge) over a
fixed background, so the animation keeps the exact identity, style and framing
of the input.

Uses Pillow for the transforms (already an optional dependency of the runtime).
"""

import io
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

CANVAS_BG = (0, 0, 0, 0)
ALPHA_THRESHOLD = 16
BG_DIFF_THRESHOLD = 48
FEATHER_RADIUS = 1.0


def _motion(action, phase):
    t = phase * 2.0 * math.pi
    if action == "walk":
        return {
            "dy": -abs(math.sin(t)) * 8,
            "dx": math.cos(t) * 3,
            "rot": math.cos(t) * 3.0,
            "sx": 1.0,
            "sy": 1.0,
        }
    if action == "run":
        return {
            "dy": -abs(math.sin(t)) * 12,
            "dx": math.cos(t) * 5,
            "rot": math.cos(t) * 4.5,
            "sx": 1.02,
            "sy": 1.04,
        }
    if action == "attack":
        k = 0.5 + 0.5 * math.cos(t)
        return {
            "dy": -abs(math.sin(t)) * 3,
            "dx": k * 18,
            "rot": k * 6.0,
            "sx": 1.0 + k * 0.02,
            "sy": 1.0 - k * 0.015,
        }
    if action == "jump":
        k = abs(math.sin(math.pi * phase))
        return {"dy": -k * 46, "dx": 0.0, "rot": 0.0, "sx": 1.0 + 0.05 * k, "sy": 1.0 - 0.05 * k}
    return {
        "dy": math.cos(t) * 5,
        "dx": 0.0,
        "rot": math.cos(t) * 2.0,
        "sx": 1.0 + 0.008 * math.cos(t),
        "sy": 1.0 + 0.012 * math.cos(t),
    }


def _fit(image, size):
    """Contain-fit onto a transparent size x size canvas."""
    image = image.convert("RGBA")
    w, h = image.size
    scale = min(size / w, size / h)
    resized = image.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), CANVAS_BG)
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2), resized)
    return canvas


def _border_bg(rgb):
    """Median colour of the canvas border -> (r,g,b)."""
    w, h = rgb.size
    step = max(1, w // 64)
    samples = []
    for x in range(0, w, step):
        samples.append(rgb.getpixel((x, 0)))
        samples.append(rgb.getpixel((x, h - 1)))
    for y in range(0, h, step):
        samples.append(rgb.getpixel((0, y)))
        samples.append(rgb.getpixel((w - 1, y)))
    return tuple(sorted(c[i] for c in samples)[len(samples) // 2] for i in range(3))


def _flood_subject(rgb):
    """Subject mask of an opaque canvas: the background is whatever a flood
    fill seeded from the borders can reach (tolerance relative to each seed's
    own colour, so gradients still fill); everything else is subject.

    Unlike a global colour diff this leaves similarly-coloured interior
    regions of the subject intact."""
    w, h = rgb.size
    work = rgb.copy()
    sentinel = (255, 0, 254)
    step = max(4, w // 16)
    seeds = [(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)]
    seeds += [(0, y) for y in range(step, h - 1, step)] + [
        (w - 1, y) for y in range(step, h - 1, step)
    ]
    for seed in seeds:
        if work.getpixel(seed) == sentinel:
            continue
        ImageDraw.floodfill(work, seed, sentinel, thresh=BG_DIFF_THRESHOLD)
    r, g, b = work.split()
    flagged = ImageChops.multiply(
        ImageChops.multiply(
            r.point(lambda v: 255 if v == 255 else 0), g.point(lambda v: 255 if v == 0 else 0)
        ),
        b.point(lambda v: 255 if v == 254 else 0),
    )
    subject = ImageChops.invert(flagged)
    # soften the cut edge so frames don't get hard jaggies
    return subject.filter(ImageFilter.GaussianBlur(FEATHER_RADIUS))


def _subject_mask(canvas):
    """-> (subject_mask L, is_transparent, background_rgb|None)."""
    alpha = canvas.getchannel("A")
    lo, hi = alpha.getextrema()
    if lo < 250 and hi > 0:
        return alpha.point(lambda a: 255 if a > ALPHA_THRESHOLD else 0), True, None

    rgb = canvas.convert("RGB")
    bg = _border_bg(rgb)
    return _flood_subject(rgb), False, bg


def _transform(sub, anchor, move):
    ax, ay = anchor
    tx, ty = move["dx"], move["dy"]
    rot = math.radians(move["rot"])
    cos_r, sin_r = math.cos(rot), math.sin(rot)
    inv_sx, inv_sy = 1.0 / move["sx"], 1.0 / move["sy"]
    m00 = cos_r * inv_sx
    m01 = sin_r * inv_sx
    m10 = -sin_r * inv_sy
    m11 = cos_r * inv_sy
    c = ax - (m00 * (ax + tx) + m01 * (ay + ty))
    f = ay - (m10 * (ax + tx) + m11 * (ay + ty))
    return sub.transform(sub.size, Image.AFFINE, (m00, m01, c, m10, m11, f), resample=Image.BICUBIC)


def animate_source(image_bytes, action="walk", frame_count=12, size=384, segment_mask=None):
    """-> (frames, reference); frames = [(w,h,RGBA)], reference = (w,h,RGBA).

    ``segment_mask``: optional precomputed subject mask (PIL "L", size x size,
    255 = subject) from an external segmenter. Only honoured for opaque
    sources — transparent PNGs already carry a perfect alpha mask. This is how
    AI-segmented subjects (complex scene backgrounds that defeat the flood
    fill) plug into the deterministic transform pipeline."""
    size = max(64, min(1024, int(size)))
    frame_count = max(2, min(48, int(frame_count)))
    original = _fit(Image.open(io.BytesIO(image_bytes)), size)

    mask, transparent, bg = _subject_mask(original)
    if segment_mask is not None and not transparent:
        mask = segment_mask.resize((size, size))
        bg = _border_bg(original.convert("RGB"))
    bbox = mask.getbbox() or (0, 0, size, size)
    # generous pad so lunges/rotations don't clip at the crop edge (the extra
    # area is harmless: the subject layer's alpha is transparent there)
    pad = 16 + int(size * 0.03)
    bx0, by0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
    bx1, by1 = min(size, bbox[2] + pad), min(size, bbox[3] + pad)

    # reference/style anchor: the untouched fitted artwork
    reference = (size, size, bytearray(original.tobytes()))

    # backdrop: original scene with the subject removed (hole filled with the
    # background colour), so the moving subject never leaves a ghost of itself.
    # The hole is punched slightly wider than the subject so leftover
    # anti-aliased edge pixels can't show as a pale outline after the move.
    hole = mask.filter(ImageFilter.MaxFilter(5)) if not transparent else mask
    base = original.copy()
    if transparent:
        base.paste(CANVAS_BG, (0, 0), hole)
    else:
        base.paste(Image.new("RGBA", original.size, (bg[0], bg[1], bg[2], 255)), (0, 0), hole)

    # subject layer: the artwork whose alpha IS the subject mask. Transforms
    # then move the character alone — an opaque source must not paste a ghost
    # rectangle of its background around (the old bug).
    sub_source = original
    if not transparent:
        sub_source = original.copy()
        sub_source.putalpha(mask)
    anchor = ((bx0 + bx1) / 2.0, float(by1))
    local_anchor = (anchor[0] - bx0, anchor[1] - by0)
    sub = sub_source.crop((bx0, by0, bx1, by1))

    frames = []
    for index in range(frame_count):
        move = _motion(action, index / frame_count)
        transformed = _transform(sub, local_anchor, move)
        frame = base.copy()
        frame.paste(transformed, (bx0, by0), transformed)
        frames.append((size, size, bytearray(frame.tobytes())))

    return frames, reference
