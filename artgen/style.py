"""Style recognition + character feature extraction + consistency scoring.

All heuristic (dependency-free) analysis over decoded RGBA pixels:

    analyze()      -> style class (2d_cel / 2d_semi / 3d_render / pixel /
                      hand_drawn), palette, line density, flatness, ...
    extract()      -> silhouette bbox, proportions, palette roles
    similarity()   -> palette / line / color / perceptual-hash agreement

The style class is used to *label* and *gate* the generated animation; the
deterministic renderer already reuses the source palette so generated frames
match by construction — the similarity check verifies it.
"""

import math

STYLE_LABELS = {
    "2d_cel": "2D 赛璐璐",
    "2d_semi": "2D 半厚涂",
    "3d_render": "3D 渲染",
    "pixel": "像素风",
    "hand_drawn": "手绘",
}


def _qcolor(r, g, b, bits=4):
    shift = 8 - bits
    return ((r >> shift) << (2 * bits)) | ((g >> shift) << bits) | (b >> shift)


def _luma(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def analyze_rgba(width, height, rgba):
    """Pixel statistics -> style profile."""
    total = width * height
    if total == 0:
        return {
            "style": "2d_semi",
            "style_label": STYLE_LABELS["2d_semi"],
            "confidence": 0.0,
            "palette_size": 0,
            "edge_density": 0.0,
            "flat_ratio": 0.0,
            "saturation": 0.0,
            "luminance_std": 0.0,
        }
    colors = set()
    sat_sum = lum_sum = lum_sq = 0.0
    edge = 0
    flat = 0
    compared = 0
    for y in range(height):
        row = y * width
        for x in range(width):
            o = (row + x) * 4
            r, g, b = rgba[o], rgba[o + 1], rgba[o + 2]
            if rgba[o + 3] < 128:
                continue
            colors.add(_qcolor(r, g, b))
            mx, mn = max(r, g, b), min(r, g, b)
            sat_sum += 0 if mx == 0 else (mx - mn) / mx
            luma = _luma(r, g, b)
            lum_sum += luma
            lum_sq += luma * luma
            if x + 1 < width:
                o2 = o + 4
                if rgba[o2 + 3] >= 128:
                    d = abs(luma - _luma(rgba[o2], rgba[o2 + 1], rgba[o2 + 2]))
                    compared += 1
                    if d > 18:
                        edge += 1
            if y + 1 < height:
                o2 = o + width * 4
                if rgba[o2 + 3] >= 128:
                    d = abs(luma - _luma(rgba[o2], rgba[o2 + 1], rgba[o2 + 2]))
                    compared += 1
                    if d > 18:
                        edge += 1
                    if abs(r - rgba[o2]) + abs(g - rgba[o2 + 1]) + abs(b - rgba[o2 + 2]) < 6:
                        flat += 1
    opaque = sum(1 for i in range(3, len(rgba), 4) if rgba[i] >= 128) or 1
    mean_lum = lum_sum / opaque
    var = max(0.0, lum_sq / opaque - mean_lum * mean_lum)
    profile = {
        "palette_size": len(colors),
        "edge_density": edge / max(1, compared),
        "flat_ratio": flat / max(1, compared),
        "saturation": sat_sum / opaque,
        "luminance_std": math.sqrt(var),
    }
    style, confidence = _classify(profile)
    profile.update(style=style, style_label=STYLE_LABELS[style], confidence=confidence)
    return profile


def _classify(profile):
    palette = profile["palette_size"]
    edge = profile["edge_density"]
    flat = profile["flat_ratio"]
    if palette < 96 and flat > 0.55:
        return "pixel", 0.74
    if palette > 2200 and edge < 0.09:
        return "3d_render", 0.7
    if edge < 0.10 and flat > 0.38:
        return "2d_cel", 0.76
    if edge > 0.16:
        return "hand_drawn", 0.62
    return "2d_semi", 0.64


def dominant_palette(width, height, rgba, count=8):
    """Most frequent quantized colours -> hex list (style transfer source)."""
    counts = {}
    for i in range(width * height):
        o = i * 4
        if rgba[o + 3] < 128:
            continue
        key = _qcolor(rgba[o], rgba[o + 1], rgba[o + 2], 4)
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:count]
    palette = []
    for key, _ in ordered:
        r = ((key >> 8) & 0xF) * 17
        g = ((key >> 4) & 0xF) * 17
        b = (key & 0xF) * 17
        palette.append("#%02x%02x%02x" % (r, g, b))
    return palette


def extract_character(width, height, rgba, metadata=None):
    """Silhouette bbox + proportions + palette roles (for feature transfer)."""
    min_x, min_y, max_x, max_y = width, height, -1, -1
    for y in range(height):
        row = y * width
        for x in range(width):
            if rgba[(row + x) * 4 + 3] >= 128:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
    if max_x < 0:
        bbox = [0, 0, width, height]
    else:
        bbox = [min_x, min_y, max_x, max_y]
    box_w = max(1, bbox[2] - bbox[0])
    box_h = max(1, bbox[3] - bbox[1])

    palette = []
    if isinstance(metadata, dict):
        roles = ((metadata.get("pixel") or {}).get("palette") or {}).get("semantic_roles") or (
            (metadata.get("source") or {}).get("palette")
        )
        if isinstance(roles, dict):
            palette = [
                roles[k]
                for k in ("outline", "base", "highlight", "accent", "hair", "skin", "eyes", "metal")
                if roles.get(k)
            ]
    return {
        "bbox": bbox,
        "size": [width, height],
        "aspect": round(box_w / box_h, 3),
        "head_ratio": 0.52,
        "center": [round((bbox[0] + bbox[2]) / 2), round((bbox[1] + bbox[3]) / 2)],
        "palette": palette,
    }


# --------------------------------------------------------------------------
# consistency / similarity
# --------------------------------------------------------------------------


def _resample(width, height, rgba, target):
    out = bytearray(target * target * 4)
    for ty in range(target):
        sy = min(height - 1, int(ty * height / target))
        for tx in range(target):
            sx = min(width - 1, int(tx * width / target))
            o = (sy * width + sx) * 4
            d = (ty * target + tx) * 4
            out[d : d + 4] = rgba[o : o + 4]
    return out


def _palette_hist(width, height, rgba, target=64):
    small = _resample(width, height, rgba, target)
    hist = {}
    for i in range(target * target):
        o = i * 4
        if small[o + 3] < 128:
            continue
        key = _qcolor(small[o], small[o + 1], small[o + 2], 3)
        hist[key] = hist.get(key, 0) + 1
    return hist


def _dhash(width, height, rgba):
    small = _resample(width, height, rgba, 9)
    bits = 0
    for y in range(8):
        for x in range(8):
            left = (y * 9 + x) * 4
            right = (y * 9 + x + 1) * 4
            if small[left + 3] < 128:
                continue
            luma_l = _luma(small[left], small[left + 1], small[left + 2])
            luma_r = _luma(small[right], small[right + 1], small[right + 2])
            if luma_l > luma_r:
                bits |= 1 << (y * 8 + x)
    return bits


def similarity_rgba(ref, frame):
    """ref/frame: (width, height, rgba). -> agreement metrics in [0,1]."""
    rw, rh, rpx = ref
    fw, fh, fpx = frame
    ra = analyze_rgba(rw, rh, rpx)
    fa = analyze_rgba(fw, fh, fpx)

    rh_hist = _palette_hist(rw, rh, rpx)
    fh_hist = _palette_hist(fw, fh, fpx)
    total_r = sum(rh_hist.values()) or 1
    total_f = sum(fh_hist.values()) or 1
    keys = set(rh_hist) | set(fh_hist)
    intersection = sum(min(rh_hist.get(k, 0) / total_r, fh_hist.get(k, 0) / total_f) for k in keys)
    palette = max(0.0, min(1.0, intersection))

    line = 1.0 - min(1.0, abs(ra["edge_density"] - fa["edge_density"]) / 0.18)

    mean_r = _mean_color(rw, rh, rpx)
    mean_f = _mean_color(fw, fh, fpx)
    dist = sum(abs(mean_r[i] - mean_f[i]) for i in range(3)) / (3 * 255)
    color = max(0.0, 1.0 - dist)

    hash_r = _dhash(rw, rh, rpx)
    hash_f = _dhash(fw, fh, fpx)
    hamming = bin(hash_r ^ hash_f).count("1")
    phash = max(0.0, 1.0 - hamming / 64.0)

    overall = round(0.40 * palette + 0.25 * color + 0.20 * line + 0.15 * phash, 4)
    return {
        "palette": round(palette, 4),
        "color": round(color, 4),
        "line": round(line, 4),
        "hash": round(phash, 4),
        "overall": overall,
    }


def _mean_color(width, height, rgba):
    r = g = b = n = 0
    for i in range(width * height):
        o = i * 4
        if rgba[o + 3] < 128:
            continue
        r += rgba[o]
        g += rgba[o + 1]
        b += rgba[o + 2]
        n += 1
    n = n or 1
    return (r // n, g // n, b // n)
