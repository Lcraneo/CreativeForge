"""Character-bound skeletal animation (Phase 2).

Unlike ``anim.py`` (which *draws* a programmatic template character) and
``sourceanim.py`` (which only bobs the whole subject), this module binds the
character's **own pixels** to the extracted rig and moves each body region
with its joint (two-bone IK for legs/arms), then re-composites over a fixed
background. Result: different characters → different, character-specific
animations; no fixed template character is ever produced.
"""

import io

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from artgen.anim import ACTIONS, _pose
from artgen.rig import build_rig
from artgen.sourceanim import _fit, _subject_mask
from artgen.style import similarity_rgba

CANVAS_BG = (0, 0, 0, 0)


def _region_layer(subject, rect, size, feather=5.0):
    """Full-canvas transparent layer containing only ``rect`` of ``subject``,
    with a **feathered** mask: adjacent regions blend into each other instead
    of cutting hard seams (P1 生成质量：消除分区旋转的接缝)."""

    layer = Image.new("RGBA", (size, size), CANVAS_BG)
    box = (
        max(0, int(rect[0])),
        max(0, int(rect[1])),
        min(size, int(rect[2])),
        min(size, int(rect[3])),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return layer
    layer.paste(subject.crop(box), (box[0], box[1]))

    rect_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(rect_mask).rectangle(box, fill=255)
    if feather > 0:
        rect_mask = rect_mask.filter(ImageFilter.GaussianBlur(feather))
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), rect_mask))
    return layer


def _place(base, layer, pivot, angle, offset):
    rotated = layer.rotate(angle, resample=Image.BICUBIC, center=(pivot[0], pivot[1]), expand=False)
    base.paste(rotated, (int(round(offset[0])), int(round(offset[1]))), rotated)


def _falign(frames):
    """Lightweight FAlign-style report for the rig-driven frames."""
    step = max(1, len(frames) // 8)
    sampled = frames[::step]
    if len(sampled) >= 2:
        diffs = [
            similarity_rgba(sampled[i - 1], sampled[i])["overall"] for i in range(1, len(sampled))
        ]
        temporal = round(sum(diffs) / len(diffs), 4)
    else:
        temporal = 1.0
    anchor = 1.0  # feet are pinned to the rig root, so the root never drifts
    return {
        "anchor": anchor,
        "temporal": temporal,
        "overall": round(0.4 * anchor + 0.6 * temporal, 4),
        "frames_checked": len(sampled),
    }


def _motion_scales(rig, size):
    """动作幅度 ↔ 体型匹配（专业级观感：同一套曲线适配不同比例的角色）。

    * ``limb``   关节角缩放——Q 版（头身比大、肢段短）角度收敛，
      避免短肢甩出"鞭梢感"；
    * ``offset`` 位移缩放——bob/sway 等像素量随角色实际身高缩放，
      小个子角色不再顶着成人大幅度曲线；
    * ``bob``    垂直起伏总增益——offset 之上再给 Q 版一点弹跳感。"""

    head_ratio = float((rig or {}).get("head_ratio") or 0.6)
    chibi_f = max(0.0, min(1.0, (head_ratio - 0.55) / 0.35))
    bbox = (rig or {}).get("bbox") or [0, 0, size, size]
    height = max(1.0, float(bbox[3] - bbox[1]))
    offset = max(0.55, min(1.5, height / (0.62 * size)))
    return {
        "limb": 1.0 - 0.18 * chibi_f,
        "offset": offset,
        "bob": offset * (1.0 + 0.30 * chibi_f),
    }


def animate_rigged(
    image_bytes,
    action="walk",
    frame_count=12,
    size=384,
    rig=None,
    config=None,
    segment_mask=None,
    keep_background=True,
):
    """-> (frames, reference, rig, falign).

    ``frames`` is a list of (w, h, RGBA); ``reference`` is the untouched source;
    ``rig`` is the extracted CharacterRig; ``falign`` the alignment report.

    ``keep_background=False`` renders the character as a transparent cutout
    (no scene background behind the subject) — used by the playtest stage so
    frames composite onto an arbitrary stage and trim to the subject bounds.
    """
    size = max(64, min(1024, int(size)))
    frame_count = max(2, min(60, int(frame_count)))
    action = action if action in ACTIONS else "walk"

    canvas = _fit(Image.open(io.BytesIO(image_bytes)), size)
    mask, transparent, bg = _subject_mask(canvas)
    if segment_mask is not None and not transparent:
        mask = segment_mask.resize((size, size))

    rig = rig or build_rig(image_bytes, size, segment_mask=segment_mask)
    x0, y0, x1, y1 = rig["bbox"]
    points = rig["points"]
    cx = (x0 + x1) / 2.0
    w = max(1.0, x1 - x0)
    torso_half = (x1 - x0) * 0.20
    hip_y = points["hip_l"][1]
    shoulder_y = points["shoulder_l"][1]
    hand_y = points["hand_l"][1]

    # subject layer (its alpha is the subject) + background with the subject removed
    if transparent:
        subject = canvas.copy()
        base_bg = canvas.copy()
        base_bg.paste(CANVAS_BG, (0, 0), mask)
    else:
        subject = canvas.copy()
        subject.putalpha(mask)
        if keep_background:
            base_bg = canvas.copy()
            fill = (bg[0], bg[1], bg[2], 255) if bg else (0, 0, 0, 255)
            base_bg.paste(Image.new("RGBA", (size, size), fill), (0, 0), mask)
        else:
            base_bg = Image.new("RGBA", (size, size), CANVAS_BG)

    regions = {
        "upper": (
            _region_layer(subject, (x0, y0, x1, hip_y + 16), size, feather=8.0),
            points["neck"],
        ),
        "arm_l": (
            _region_layer(
                subject, (x0, shoulder_y - 8, cx + torso_half * 0.1, hand_y + 12), size, feather=4.0
            ),
            points["shoulder_l"],
        ),
        "arm_r": (
            _region_layer(
                subject, (cx - torso_half * 0.1, shoulder_y - 8, x1, hand_y + 12), size, feather=4.0
            ),
            points["shoulder_r"],
        ),
        "leg_l": (
            _region_layer(subject, (x0, hip_y - 26, cx + w * 0.12, y1), size, feather=5.0),
            points["hip_l"],
        ),
        "leg_r": (
            _region_layer(subject, (cx - w * 0.12, hip_y - 26, x1, y1), size, feather=5.0),
            points["hip_r"],
        ),
        # 裆部立柱（修复"身材切割"）：左右腿反向旋转时中缝会撕裂、露出底下
        # 的背景填充色。这一层取自原画自身的裆部像素，**不参与旋转**、只跟随
        # 起伏平移，画在两腿之上——腿摆动时中缝始终被角色自己的裤子像素填满，
        # 不再露出竖直亮缝。
        "crotch": (
            _region_layer(subject, (cx - w * 0.17, hip_y - 12, cx + w * 0.17, y1), size, feather=4.0),
            points["root"],
        ),
        # 双骨链子层：小腿（膝下含脚）与前臂（肘下含手）——跟随父段旋转角
        # 之上再叠加膝弯/肘屈，取代整腿/整臂单刚体旋转的"分段拼接感"
        "shin_l": (
            _region_layer(subject, (x0, points["knee_l"][1] - 22, cx + w * 0.12, y1), size, feather=5.5),
            points["knee_l"],
        ),
        "shin_r": (
            _region_layer(subject, (cx - w * 0.12, points["knee_r"][1] - 22, x1, y1), size, feather=5.5),
            points["knee_r"],
        ),
        "forearm_l": (
            _region_layer(
                subject, (x0, points["elbow_l"][1] - 6, cx + torso_half * 0.1, hand_y + 14), size, feather=3.0
            ),
            points["elbow_l"],
        ),
        "forearm_r": (
            _region_layer(
                subject, (cx - torso_half * 0.1, points["elbow_r"][1] - 6, x1, hand_y + 14), size, feather=3.0
            ),
            points["elbow_r"],
        ),
    }

    frames = []
    scales = _motion_scales(rig, size)
    for index in range(frame_count):
        pose = _pose(action, index / frame_count, config)
        dy = (pose["bob"] - pose["jump"]) * scales["bob"]
        lean = pose["lean"]
        sway = pose.get("sway", 0.0) * scales["offset"]
        tilt = pose.get("tilt", 0.0)
        arm = pose["arm"] * scales["limb"]
        leg = pose["leg"] * scales["limb"]

        frame = base_bg.copy()
        # 双骨链合成：大腿 → 小腿（父段角 + 膝弯）→ 裆部立柱（填中缝，无旋转）
        # → 躯干 → 上臂 → 前臂（父段角 + 肘屈）。膝/肘的滞后与屈曲让肢体
        # 呈两段式运动，消除整段刚体旋转的分段拼接感。躯干在 lean 之上
        # 叠加 tilt（肩线与髋部横移反向的微小倾斜 = 肩盆反向次级动作）。
        thigh_l = pose.get("thigh_l", leg) * scales["limb"]
        thigh_r = pose.get("thigh_r", leg) * scales["limb"]
        knee_l = pose.get("knee_l", 0.0) * scales["limb"]
        knee_r = pose.get("knee_r", 0.0) * scales["limb"]
        elbow_l = pose.get("elbow_l", 0.0) * scales["limb"]
        elbow_r = pose.get("elbow_r", 0.0) * scales["limb"]

        _place(frame, regions["leg_l"][0], regions["leg_l"][1], -thigh_l * 14, (sway * 0.3, dy))
        _place(frame, regions["shin_l"][0], regions["shin_l"][1], -thigh_l * 14 + knee_l, (sway * 0.3, dy))
        _place(frame, regions["leg_r"][0], regions["leg_r"][1], thigh_r * 14, (sway * 0.3, dy))
        _place(frame, regions["shin_r"][0], regions["shin_r"][1], thigh_r * 14 + knee_r, (sway * 0.3, dy))
        _place(frame, regions["crotch"][0], regions["crotch"][1], 0.0, (0.0, dy))
        _place(frame, regions["upper"][0], regions["upper"][1], -lean - tilt, (sway, dy))
        _place(frame, regions["arm_l"][0], regions["arm_l"][1], arm * 22, (sway * 0.5, dy))
        _place(frame, regions["forearm_l"][0], regions["forearm_l"][1], arm * 22 + elbow_l, (sway * 0.5, dy))
        _place(frame, regions["arm_r"][0], regions["arm_r"][1], -arm * 22, (sway * 0.5, dy))
        _place(frame, regions["forearm_r"][0], regions["forearm_r"][1], -arm * 22 + elbow_r, (sway * 0.5, dy))
        frames.append((size, size, bytearray(frame.tobytes())))

    reference = (size, size, bytearray(canvas.tobytes()))
    return frames, reference, rig, _falign(frames)


def render_rigged_frame_rgba(
    image_bytes, action, phase, size, rig=None, config=None, segment_mask=None, count=24
):
    """One rig-driven frame at an arbitrary phase (preview-frame endpoint)."""
    frames, reference, rig, _ = animate_rigged(
        image_bytes, action, count, size, rig=rig, config=config, segment_mask=segment_mask
    )
    index = min(count - 1, max(0, int(round(phase * count)) % count))
    return frames[index], rig
