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

from PIL import Image

CANVAS_BG = (0, 0, 0, 0)
ALPHA_THRESHOLD = 16
BG_DIFF_THRESHOLD = 48


def _motion(action, phase):
    t = phase * 2.0 * math.pi
    if action == "walk":
        return {"dy": -abs(math.sin(t)) * 6, "dx": math.cos(t) * 3, "rot": math.cos(t) * 3.0, "sx": 1.0, "sy": 1.03}
    if action == "run":
        return {"dy": -abs(math.sin(t)) * 10, "dx": math.cos(t) * 5, "rot": math.cos(t) * 5.0, "sx": 1.02, "sy": 1.05}
    if action == "attack":
        k = 0.5 + 0.5 * math.cos(t)
        return {"dy": -abs(math.sin(t)) * 3, "dx": k * 20, "rot": k * 7.0, "sx": 1.0 + k * 0.03, "sy": 1.0 - k * 0.02}
    if action == "jump":
        k = abs(math.sin(math.pi * phase))
        return {"dy": -k * 42, "dx": 0.0, "rot": 0.0, "sx": 1.0 + 0.05 * k, "sy": 1.0 - 0.05 * k}
    return {"dy": math.cos(t) * 4, "dx": 0.0, "rot": math.cos(t) * 1.5,
            "sx": 1.0 + 0.008 * math.cos(t), "sy": 1.0 + 0.012 * math.cos(t)}


def _fit(image, size):
    """Contain-fit onto a transparent size x size canvas."""
    image = image.convert("RGBA")
    w, h = image.size
    scale = min(size / w, size / h)
    resized = image.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), CANVAS_BG)
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2), resized)
    return canvas


def _subject_mask(canvas):
    """-> (subject_mask L, is_transparent, background_rgb|None)."""
    alpha = canvas.getchannel("A")
    lo, hi = alpha.getextrema()
    if lo < 250 and hi > 0:
        return alpha.point(lambda a: 255 if a > ALPHA_THRESHOLD else 0), True, None

    w, h = canvas.size
    rgb = canvas.convert("RGB")
    step = max(1, w // 64)
    samples = []
    for x in range(0, w, step):
        samples.append(rgb.getpixel((x, 0)))
        samples.append(rgb.getpixel((x, h - 1)))
    for y in range(0, h, step):
        samples.append(rgb.getpixel((0, y)))
        samples.append(rgb.getpixel((w - 1, y)))
    bg = tuple(sorted(c[i] for c in samples)[len(samples) // 2] for i in range(3))

    diff = Image.new("L", (w, h))
    out = diff.load()
    src = rgb.load()
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            out[x, y] = 255 if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > BG_DIFF_THRESHOLD else 0
    return diff, False, bg


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


def animate_source(image_bytes, action="walk", frame_count=12, size=384):
    """-> (frames, reference); frames = [(w,h,RGBA)], reference = (w,h,RGBA)."""
    size = max(64, min(1024, int(size)))
    frame_count = max(2, min(48, int(frame_count)))
    canvas = _fit(Image.open(io.BytesIO(image_bytes)), size)

    mask, transparent, bg = _subject_mask(canvas)
    bbox = mask.getbbox() or (0, 0, size, size)
    pad = 12
    bx0, by0 = max(0, bbox[0] - pad), max(0, bbox[1] - pad)
    bx1, by1 = min(size, bbox[2] + pad), min(size, bbox[3] + pad)
    sub = canvas.crop((bx0, by0, bx1, by1))
    anchor = ((bx0 + bx1) / 2.0, float(by1))
    local_anchor = (anchor[0] - bx0, anchor[1] - by0)

    # background with the subject removed (keeps composition fixed)
    base = canvas.copy()
    if transparent:
        base.paste(CANVAS_BG, (0, 0), mask)
    else:
        base.paste(Image.new("RGBA", canvas.size, (bg[0], bg[1], bg[2], 255)), (0, 0), mask)

    frames = []
    for index in range(frame_count):
        move = _motion(action, index / frame_count)
        transformed = _transform(sub, local_anchor, move)
        frame = base.copy()
        frame.paste(transformed, (bx0, by0), transformed)
        frames.append((size, size, bytearray(frame.tobytes())))

    return frames, (size, size, bytearray(canvas.tobytes()))
