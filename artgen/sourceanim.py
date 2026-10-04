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


def edge_smoothness(mask):
    """边缘软度（V3 边缘质量指标）：alpha 边界上「过渡像素」占比 0..1。

    硬边（0/255 二值跳变）→ 0；纯渐变带 → 接近 1。计算：邻域梯度
    |∇alpha| 的边界像素中，非满跳变（<255）的比例。用于量化羽化质量、
    对比不同羽化策略，不设业务阈值。"""
    import numpy as np

    a = np.asarray(mask, dtype=np.int16)
    gx = np.zeros_like(a)
    gy = np.zeros_like(a)
    gx[:, :-1] = np.abs(a[:, 1:] - a[:, :-1])
    gy[:-1, :] = np.abs(a[1:, :] - a[:-1, :])
    grad = np.maximum(gx, gy)
    edge = grad > 0
    total = int(edge.sum())
    if not total:
        return 1.0  # 无边界（全透明/全实心）视为无锯齿
    smooth = int((grad[edge] < 255).sum())
    return round(smooth / total, 4)


def edge_halo_px(mask, binary):
    """外溢 halo（V3 边缘质量指标）：羽化后 alpha≥128 的像素落到原二值
    mask 之外的像素数。越大 = 角色边缘外圈带出一圈背景色。0 为理想。"""
    import numpy as np

    soft = np.asarray(mask) >= 128
    hard = np.asarray(binary) >= 128
    return int((soft & ~hard).sum())


def refine_edge_alpha(image, mask, bg=(255, 255, 255), band=2.0):
    """白底 alpha 反解（V3 matting 精修·路线 A）：边界带内按合成方程
    反解每个像素的真实 alpha 与前景色。

    原理：白底素材的边缘像素色 C = F·t + bg·(1−t)（t=真实覆盖度）。旧
    路径保留 C 只调 alpha=mask 羽化——合成到新底时旧底色以 (1−t)·t 残留
    （边缘发灰/泛白）。本函数在边界带内求解 α 与 F=(C−(1−α)·bg)/α，把
    "带底色的边缘像素"还原成"纯前景 + 真 alpha"，合成到任意底都干净。

    前景色 F 由 solid 内部（mask≥250）向边界逐格传播（band+1 轮邻域均
    值）；|F−bg| 过小（前景与底同色，歧义像素如白衣贴白底）时保留原值
    不解。仅边界带被改写，内部/外部像素原样返回。输入 mask 可为二值或
    羽化后（内部判定统一取 ≥250）。返回 RGBA Image。"""
    import numpy as np
    from PIL import Image, ImageFilter

    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    m = np.asarray(mask, dtype=np.float32)
    solid = m >= 250
    bg_arr = np.array(bg, dtype=np.float32)

    # 内距分级：dist=0 为 solid 内部，k = 距内部 k 像素（erosion 反向）
    steps = max(1, int(np.ceil(band)) + 1)
    levels = np.zeros(m.shape, dtype=np.int32)
    current = solid.copy()
    for k in range(1, steps + 1):
        eroded = np.asarray(
            Image.fromarray((current * 255).astype(np.uint8), "L").filter(
                ImageFilter.MinFilter(3)
            ),
            dtype=np.uint8,
        ) >= 128
        levels[~current & ~eroded & (levels == 0)] = k
        current = eroded
    zone = (levels > 0) & (levels <= steps)

    # 前景色传播：从 solid 向外逐轮填充邻域均值
    fg = rgb.copy()
    known = solid.copy()
    for _ in range(steps):
        acc = np.zeros_like(fg)
        cnt = np.zeros(m.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            shifted = np.roll(np.roll(fg, dy, axis=0), dx, axis=1)
            shifted_known = np.roll(np.roll(known, dy, axis=0), dx, axis=1)
            acc += shifted * shifted_known[..., None]
            cnt += shifted_known
        fill = (cnt > 0) & ~known
        fg[fill] = acc[fill] / cnt[fill][..., None]
        known = known | fill

    # 合成方程反解：C = F·α + bg·(1−α) → α = (C−bg)·(F−bg) / |F−bg|²
    fb = fg - bg_arr[None, None, :]
    denom = (fb * fb).sum(axis=-1)
    cb = rgb - bg_arr[None, None, :]
    alpha = np.where(
        denom > 900.0,  # |F−bg| > 30：前景与底色可分才可靠
        (cb * fb).sum(axis=-1) / np.maximum(denom, 1e-6),
        -1.0,
    )
    alpha = np.clip(alpha, 0.0, 1.0)

    out_rgb = rgb.copy()
    out_a = m / 255.0
    solvable = zone & (alpha >= 0.0)
    out_a[solvable] = alpha[solvable]
    fg_rec = (rgb - bg_arr[None, None, :] * (1.0 - out_a[..., None])) / np.maximum(
        out_a[..., None], 1.0 / 255.0
    )
    out_rgb = np.where(solvable[..., None], np.clip(fg_rec, 0, 255), out_rgb)

    rgba = np.dstack([out_rgb, out_a * 255.0]).astype(np.uint8)
    result = Image.fromarray(rgba, "RGBA")
    # 0.6px 轻平滑消反解阶梯（alpha 与色同步平滑，不引入新底色）
    return result.filter(ImageFilter.GaussianBlur(0.6))


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
    # soften the cut edge so frames don't get hard jaggies。V3 加了边缘质量
    # 指标（edge_smoothness/edge_halo_px）建立度量基线；实测距离分级 ramp
    # 在 band=2 时是色带阶梯、不如 blur 的连续钟形，故羽化维持 GaussianBlur
    # ——真正的 matting 升级（AI matting / 分数距离变换）留待下批做对。
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
    # 与 pipeline.create_animation 同口径：放行 24fps 整循环（原 48 封顶）
    frame_count = max(2, min(90, int(frame_count)))
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
