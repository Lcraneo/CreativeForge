"""Character Rig extraction (Phase 2).

Builds a lightweight, **character-specific** skeleton from the current source
image (asset 原画 / 上传图) instead of assuming a shared template. The rig is
derived from the subject silhouette + proportional landmarks, so two different
characters produce two different rigs (different ``source_hash`` and joint
layout) — which is what lets the skeletal animation move *this* character
rather than a fixed programmatic one.

Output (a plain dict, JSON-serialisable)::

    {
      "bbox": [x0, y0, x1, y1],
      "size": [canvas_w, canvas_h],
      "source_size": [w, h],          # original image size
      "transparent": bool,
      "confidence": float,
      "source_hash": "12hex",
      "points": { "root": [x,y], "head": [x,y], ... }
    }

Joints: root, head, neck, shoulder_l/r, elbow_l/r, hand_l/r,
hip_l/r, knee_l/r, foot_l/r (17 points).
"""

import hashlib
import io

from PIL import Image

from artgen.sourceanim import _fit, _subject_mask

POINT_ORDER = (
    "root",
    "head",
    "neck",
    "shoulder_l",
    "elbow_l",
    "hand_l",
    "shoulder_r",
    "elbow_r",
    "hand_r",
    "hip_l",
    "knee_l",
    "foot_l",
    "hip_r",
    "knee_r",
    "foot_r",
)


def _extent(mask, y0, y1):
    """(min_x, max_x) of opaque subject pixels within rows [y0, y1)."""
    width, height = mask.size
    pixels = mask.load()
    min_x, max_x = width, -1
    for y in range(max(0, y0), min(height, y1)):
        for x in range(width):
            if pixels[x, y] > 128:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
    if max_x < 0:
        return None
    return min_x, max_x


def _column_runs(mask, y0, y1, min_gap=3):
    """Contiguous opaque column runs within rows [y0, y1), widened by min_gap.

    Used to separate the two feet at the very bottom of the subject: feet
    usually stand on slightly different ground lines, so scanning only the
    last 3 rows (the old foot probe) collapses onto whichever foot is lower
    and both foot/hand landmarks pile up on one side."""
    width, height = mask.size
    pixels = mask.load()
    cols = bytearray(width)
    for y in range(max(0, y0), min(height, y1)):
        for x in range(width):
            if pixels[x, y] > 128:
                cols[x] = 1
    runs = []
    start = None
    gap = 0
    for x in range(width + 1):
        on = cols[x] if x < width else 0
        if on:
            if start is None:
                start = x
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap or x == width:
                runs.append((start, x - gap))
                start = None
    return runs


def build_rig(image_bytes, size=384, segment_mask=None):
    """Extract a CharacterRig from an image (PNG/JPEG/WebP bytes)."""
    size = max(64, min(1024, int(size)))
    original = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    source_size = list(original.size)
    canvas = _fit(original, size)

    mask, transparent, bg = _subject_mask(canvas)
    if segment_mask is not None and not transparent:
        mask = segment_mask.resize((size, size))

    bbox = mask.getbbox() or (0, 0, size, size)
    x0, y0, x1, y1 = bbox
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    cx = (x0 + x1) / 2.0

    def band(ratio):
        return int(y0 + h * ratio)

    shoulder_y = band(0.42)
    hip_y = band(0.60)
    knee_y = band(0.78)
    foot_y = float(y1 - 1)

    shoulder = _extent(mask, shoulder_y - 2, shoulder_y + 3) or (
        int(cx - w * 0.30),
        int(cx + w * 0.30),
    )
    hip = _extent(mask, hip_y - 2, hip_y + 3) or (int(cx - w * 0.18), int(cx + w * 0.18))

    # ── 双脚分离探测 ─────────────────────────────────────────────
    # 旧探测只扫最后 3 行：两脚 ground line 略有高低（透视/站姿常态）
    # 时塌到更低那只脚上，foot/hand 全部挤到一侧（实测 hand_l/hand_r
    # 同 x≈237）。改扫底部 8 行按列段分离，取最宽的两段作左右脚。
    foot_runs = [r for r in _column_runs(mask, int(foot_y) - 7, int(foot_y) + 1) if r[1] > r[0]]
    if len(foot_runs) >= 2:
        widest = sorted(foot_runs, key=lambda run: run[1] - run[0], reverse=True)[:2]
        widest.sort(key=lambda run: run[0])
        left_run, right_run = widest
        foot = (left_run[0], right_run[1])
        foot_l_x = (left_run[0] + left_run[1]) / 2.0
        foot_r_x = (right_run[0] + right_run[1]) / 2.0
    else:
        foot = _extent(mask, int(foot_y) - 3, int(foot_y)) or (
            int(cx - w * 0.20),
            int(cx + w * 0.20),
        )
        foot_l_x = foot[0] + (foot[1] - foot[0]) * 0.20
        foot_r_x = foot[1] - (foot[1] - foot[0]) * 0.20

    # ── 膝线:行宽剖面收窄检测 ────────────────────────────────────
    # 比例带 0.78 只对标准站姿成立；长腿/束脚角色膝线系统性偏上，小腿层
    # 从大腿中段就被切走。在 [hip, foot] 剖面上找显著收窄行（膝/靴口），
    # 剖面平坦（宽腿裤）或位置离谱时回退先验。
    profile_lo = int(hip_y)
    profile = []
    for yy in range(profile_lo, int(y1)):
        row = _extent(mask, yy, yy + 1)
        profile.append((row[1] - row[0]) if row else 0)
    seg_start = int(len(profile) * 0.35)  # 避开大腿根与臀部最宽处
    seg = profile[seg_start:]
    if seg:
        narrow = min(seg)
        narrow_pos = profile_lo + seg_start + seg.index(narrow)
        median_w = sorted(seg)[len(seg) // 2]
        narrow_ratio = narrow_pos / max(1.0, h)
        credible = narrow <= median_w * 0.88 and 0.68 <= narrow_ratio <= 0.90
        in_band = (
            profile_lo + 0.30 * (y1 - profile_lo) <= narrow_pos <= y1 - max(4.0, 0.06 * h)
        )
        if credible and in_band:
            knee_y = float(narrow_pos)

    shoulder_span = max(1.0, shoulder[1] - shoulder[0])
    hip_span = max(1.0, hip[1] - hip[0])

    # ── 头身比检测（Q 版识别）───────────────────────────────────────
    # 比例带（肩 42% / 髋 60%）只对六七头身成立；Q 版二头身角色关节会
    # 系统性错位。用逐行宽度剖面找"颈线"：头高占比 > 33% 或 头宽≈躯干宽
    # 即判为 chibi，置信度减半并向上游暴露，供前端建议改用 AI 视频驱动。
    pixels = mask.load()
    widths = []
    for y in range(y0, y1):
        row_w = sum(1 for x in range(x0, x1) if pixels[x, y] > 128)
        widths.append(row_w)
    # 颈线搜索：跳过头顶弧线（前 12%），在 12%~55% 高度内找最窄行（颈部）
    search_lo = max(1, int(len(widths) * 0.12))
    search_hi = max(search_lo + 4, int(len(widths) * 0.55))
    upper_band = widths[search_lo:search_hi]
    neck_index = (
        search_lo + upper_band.index(min(upper_band)) if upper_band else int(len(widths) * 0.3)
    )
    head_h = neck_index / max(1, len(widths))
    head_w = max(widths[: max(1, neck_index + 1)], default=0)
    torso_w = max(widths[neck_index:], default=0)
    head_ratio = head_w / max(1, torso_w)
    chibi = head_h > 0.33 or head_ratio > 0.85
    proportion = "chibi" if chibi else "normal"

    def point(x, y):
        return [round(float(x), 1), round(float(y), 1)]

    points = {
        "root": point(cx, foot_y),
        "head": point(cx, y0 + h * 0.18),
        "neck": point(cx, band(0.38)),
        "shoulder_l": point(shoulder[0] + shoulder_span * 0.10, shoulder_y),
        "shoulder_r": point(shoulder[1] - shoulder_span * 0.10, shoulder_y),
        "elbow_l": point(shoulder[0] + shoulder_span * 0.02, band(0.53)),
        "elbow_r": point(shoulder[1] - shoulder_span * 0.02, band(0.53)),
        "hand_l": point(shoulder[0] + shoulder_span * 0.06, band(0.66)),
        "hand_r": point(shoulder[1] - shoulder_span * 0.06, band(0.66)),
        "hip_l": point(hip[0] + hip_span * 0.16, hip_y),
        "hip_r": point(hip[1] - hip_span * 0.16, hip_y),
        "knee_l": point(hip[0] + hip_span * 0.18, knee_y),
        "knee_r": point(hip[1] - hip_span * 0.18, knee_y),
        "foot_l": point(foot_l_x, foot_y),
        "foot_r": point(foot_r_x, foot_y),
    }

    confidence = 0.92 if transparent else (0.7 if mask.getbbox() else 0.45)
    if chibi:
        confidence = round(confidence * 0.45, 3)
    return {
        "bbox": [x0, y0, x1, y1],
        "size": [size, size],
        "source_size": source_size,
        "transparent": bool(transparent),
        "confidence": confidence,
        "proportion": proportion,
        "head_ratio": round(head_ratio, 3),
        "head_height": round(head_h, 3),
        "source_hash": hashlib.sha1(bytes(image_bytes)).hexdigest()[:12],
        "points": points,
    }


def rig_summary(rig):
    """Small, API-friendly view of a rig (no full point table)."""
    return {
        "source_hash": rig["source_hash"],
        "bbox": rig["bbox"],
        "source_size": rig["source_size"],
        "confidence": rig["confidence"],
        "joints": len(rig["points"]),
    }
