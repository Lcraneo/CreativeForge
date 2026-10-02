"""Character-bound skeletal animation (Phase 2).

Unlike ``anim.py`` (which *draws* a programmatic template character) and
``sourceanim.py`` (which only bobs the whole subject), this module binds the
character's **own pixels** to the extracted rig and moves each body region
with its joint (two-bone IK for legs/arms), then re-composites over a fixed
background. Result: different characters → different, character-specific
animations; no fixed template character is ever produced.
"""

import io

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from artgen.anim import ACTIONS, _pose
from artgen.rig import build_rig
from artgen.sourceanim import BG_DIFF_THRESHOLD, _fit, _subject_mask
from artgen.style import similarity_rgba

CANVAS_BG = (0, 0, 0, 0)


def _absorb_enclosed_background(mask, rgb, bg_color=None):
    """把主体内与背景色同色的**封闭区**回收为背景（分体修复 R1）。

    洪泛抠图（_flood_subject）从画布边缘出发，只能吃掉与边缘**连通**的
    背景；被肢体围住的背景洞——两腿之间、脚与阴影围出的区域——不可达，
    会被误判成主体。分区旋转动画里，这些洞像素落进腿/躯干区域层跟着
    旋转平移，就是试玩舞台"蓝色色块飘移/身体分体"的根因。

    ``bg_color``：背景参考色（默认取画布边缘中值色；AI 分割路径的契约
    是纯白底，调用方显式传 (255,255,255)）。

    判据（三条件同时满足才回收，避免误伤与背景撞色的服装）：
      1. 当前被标记为主体；
      2. 颜色与背景参考色的逐通道差 ≤ BG_DIFF_THRESHOLD（与洪泛同口径）；
      3. 所属连通域**不接触**画布边缘（接触边缘的保留不动，保守处理
         渐变背景漏吃的情况）。

    任何失败返回原 mask（该修复永不阻塞动画生成）。"""

    try:
        subject = np.asarray(mask, dtype=np.uint8) > 128
        if not subject.any():
            return mask
        rgb_arr = np.asarray(rgb.convert("RGB"), dtype=np.int16)
        if rgb_arr.shape[:2] != subject.shape:
            return mask
        if bg_color is None:
            from artgen.sourceanim import _border_bg

            bg_color = _border_bg(rgb)
        bg = np.array(bg_color, dtype=np.int16)
        color_ok = np.abs(rgb_arr - bg[None, None, :]).max(axis=2) <= BG_DIFF_THRESHOLD
        candidates = subject & color_ok
        if not candidates.any():
            return mask

        border_touch = np.zeros_like(candidates)
        border_touch[0, :] = border_touch[-1, :] = True
        border_touch[:, 0] = border_touch[:, -1] = True

        absorbed = np.zeros_like(candidates)
        remaining = candidates & ~border_touch
        # 向量 BFS：从任意未访问种子做二值传播标注连通域
        while remaining.any():
            ys, _xs = np.nonzero(remaining)
            frontier = np.zeros_like(candidates)
            frontier[int(ys[0]), int(_xs[0])] = True
            comp = np.zeros_like(candidates)
            while frontier.any():
                comp |= frontier
                grew = np.zeros_like(candidates)
                grew[1:, :] |= frontier[:-1, :]
                grew[:-1, :] |= frontier[1:, :]
                grew[:, 1:] |= frontier[:, :-1]
                grew[:, :-1] |= frontier[:, 1:]
                frontier = grew & candidates & ~comp
            absorbed |= comp
            remaining = candidates & ~absorbed

        if not absorbed.any():
            return mask

        cleaned = np.asarray(mask).copy()
        cleaned[absorbed] = 0
        result = Image.fromarray(cleaned, mode="L")
        # 回收边界补羽化，与主体切边同质感
        return result.filter(ImageFilter.GaussianBlur(1.0))
    except Exception:  # noqa: BLE001 - 修复永不阻塞动画生成
        return mask


def _region_layer(subject, rect, size, feather=5.0, exclude_above=None):
    """Full-canvas transparent layer containing only ``rect`` of ``subject``,
    with a **feathered** mask: adjacent regions blend into each other instead
    of cutting hard seams (P1 生成质量：消除分区旋转的接缝).

    ``exclude_above``：头部保护区 y 值（分体修复 R2）——该 y 之上的像素
    全部置透明。手臂/前臂区域是横跨半身的矩形，Q 版角色（头占比大）的
    脸会落进手臂矩形，摆臂时把脸"片"走（试玩区实测的脸部横向切片）。
    """

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
    if exclude_above is not None and exclude_above > 0:
        # 保护区在羽化**之后**硬归零：羽化的上侧扩散会把贴近下巴的脸部
        # 像素以 0.2~0.5 的 alpha 漏进手臂层（实测漏出 ~7px 的刚性偏差），
        # 归零只保留羽化在下侧的接缝过渡
        ImageDraw.Draw(rect_mask).rectangle((0, 0, size, int(exclude_above)), fill=0)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), rect_mask))
    return layer


def _place(base, layer, pivot, angle, offset):
    rotated = layer.rotate(angle, resample=Image.BICUBIC, center=(pivot[0], pivot[1]), expand=False)
    base.paste(rotated, (int(round(offset[0])), int(round(offset[1]))), rotated)
    return rotated


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
    if not transparent:
        # 分体修复 R1：洪泛/AI 分割都可能把"被肢体围住的封闭背景洞"
        # 误判成主体（两腿之间露出的原背景色）。洞像素在画布上显示的
        # 就是原背景色，两条路径都用洪泛的边缘中值色作参考。
        mask = _absorb_enclosed_background(mask, canvas, bg_color=bg)

    rig = rig or build_rig(image_bytes, size, segment_mask=segment_mask)
    x0, y0, x1, y1 = rig["bbox"]
    points = rig["points"]
    cx = (x0 + x1) / 2.0
    w = max(1.0, x1 - x0)
    torso_half = (x1 - x0) * 0.20
    hip_y = points["hip_l"][1]
    shoulder_y = points["shoulder_l"][1]
    hand_y = points["hand_l"][1]
    # 头部保护区（分体修复 R2）：Q 版角色（头占比大）的肩带落在脸上，
    # 手臂/前臂区域矩形横穿面部，摆臂会把脸"片"走（试玩区实测的脸部
    # 横向切片）。颈线检测比例给出真实下巴位置；normal 角色钳到 0.30
    # 后低于肩带（42%），行为与修复前一致。
    head_h = max(0.30, min(0.75, float(rig.get("head_height") or 0.30)))
    chin_y = y0 + head_h * (y1 - y0) + 2.0

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
                subject,
                (x0, shoulder_y - 8, cx + torso_half * 0.1, min(y1, points["elbow_l"][1] + 6)),
                size,
                feather=4.0,
                exclude_above=chin_y,
            ),
            points["shoulder_l"],
        ),
        "arm_r": (
            _region_layer(
                subject,
                (cx - torso_half * 0.1, shoulder_y - 8, x1, min(y1, points["elbow_r"][1] + 6)),
                size,
                feather=4.0,
                exclude_above=chin_y,
            ),
            points["shoulder_r"],
        ),
        # 帧粘连修复（分区独占所有权）：父段层只拥有自己的肢段——大腿层裁到
        # 膝（膝下像素只由小腿层渲染）、上臂层裁到肘（肘下只由前臂层渲染）。
        # 旧版父段层含整肢像素：膝弯/肘屈时父段层里那份"肢端拷贝"仍按父段
        # 角刚体旋转，与小腿/前臂层的弯角渲染同屏叠加——就是试玩区/工作台
        # 实测的"上一帧骨骼姿态残留 + 顶点裂变 + 拖影"。焊缝由子层顶部 22px
        # 的羽化搭接带吸收（子层绕关节旋转，关节处位移≈0）。
        "leg_l": (
            _region_layer(
                subject,
                (x0, hip_y - 26, cx + w * 0.12, min(y1, points["knee_l"][1] + 8)),
                size,
                feather=5.0,
            ),
            points["hip_l"],
        ),
        "leg_r": (
            _region_layer(
                subject,
                (cx - w * 0.12, hip_y - 26, x1, min(y1, points["knee_r"][1] + 8)),
                size,
                feather=5.0,
            ),
            points["hip_r"],
        ),
        # 裆部立柱（修复"身材切割"）：左右腿反向旋转时中缝会撕裂、露出底下
        # 的背景填充色。这一层取自原画自身的裆部像素，**不参与旋转**——且
        # 只做"填洞者"：逐帧用已绘制覆盖图门控，只贴到两条大腿摆开后露出的
        # 楔形空隙里，绝不压在运动中的腿上（旧版矩形一路到脚底、整列原姿态
        # 腿像素盖在每一帧上，正是"初始骨骼状态残留"的来源）。矩形也裁到
        # 膝：膝下的填缝属于小腿层的事。
        "crotch": (
            _region_layer(
                subject,
                (
                    cx - w * 0.17,
                    hip_y - 12,
                    cx + w * 0.17,
                    min(y1, points["knee_l"][1] + 6),
                ),
                size,
                feather=4.0,
            ),
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
                subject,
                (x0, points["elbow_l"][1] - 6, cx + torso_half * 0.1, hand_y + 14),
                size,
                feather=3.0,
                exclude_above=chin_y,
            ),
            points["elbow_l"],
        ),
        "forearm_r": (
            _region_layer(
                subject,
                (cx - torso_half * 0.1, points["elbow_r"][1] - 6, x1, hand_y + 14),
                size,
                feather=3.0,
                exclude_above=chin_y,
            ),
            points["elbow_r"],
        ),
    }

    frames = []
    scales = _motion_scales(rig, size)

    coverage = Image.new("L", (size, size), 0)

    def _place_tracked(layer, pivot, angle, offset):
        """贴层并累计"已绘制覆盖图"——裆部立柱只填洞门控的依据。"""
        nonlocal coverage
        rotated = _place(frame, layer, pivot, angle, offset)
        ox, oy = int(round(offset[0])), int(round(offset[1]))
        blank = Image.new("RGBA", (size, size), CANVAS_BG)
        blank.paste(rotated, (ox, oy))
        grown = np.maximum(
            np.asarray(coverage, dtype=np.uint8),
            np.asarray(blank.getchannel("A"), dtype=np.uint8),
        )
        coverage = Image.fromarray(grown, "L")

    for index in range(frame_count):
        pose = _pose(action, index / frame_count, config)
        dy = (pose["bob"] - pose["jump"]) * scales["bob"]
        lean = pose["lean"]
        sway = pose.get("sway", 0.0) * scales["offset"]
        tilt = pose.get("tilt", 0.0)
        arm = pose["arm"] * scales["limb"]
        leg = pose["leg"] * scales["limb"]

        frame = base_bg.copy()
        # 双骨链合成：大腿 → 小腿（父段角 + 膝弯）→ 裆部立柱（只填洞，无
        # 旋转）→ 躯干 → 上臂 → 前臂（父段角 + 肘屈）。膝/肘的滞后与屈曲让
        # 肢体呈两段式运动，消除整段刚体旋转的分段拼接感。父段层已裁到膝/肘
        # （分区独占所有权），焊缝由子层顶部羽化搭接带吸收；躯干在 lean 之上
        # 叠加 tilt（肩线与髋部横移反向的微小倾斜 = 肩盆反向次级动作）。
        thigh_l = pose.get("thigh_l", leg) * scales["limb"]
        thigh_r = pose.get("thigh_r", leg) * scales["limb"]
        knee_l = pose.get("knee_l", 0.0) * scales["limb"]
        knee_r = pose.get("knee_r", 0.0) * scales["limb"]
        elbow_l = pose.get("elbow_l", 0.0) * scales["limb"]
        elbow_r = pose.get("elbow_r", 0.0) * scales["limb"]

        _place_tracked(regions["leg_l"][0], regions["leg_l"][1], -thigh_l * 14, (sway * 0.3, dy))
        _place_tracked(
            regions["shin_l"][0], regions["shin_l"][1], -thigh_l * 14 + knee_l, (sway * 0.3, dy)
        )
        _place_tracked(regions["leg_r"][0], regions["leg_r"][1], thigh_r * 14, (sway * 0.3, dy))
        _place_tracked(
            regions["shin_r"][0], regions["shin_r"][1], thigh_r * 14 + knee_r, (sway * 0.3, dy)
        )
        # 裆部立柱"只填洞"：门控 = 立柱 alpha × NOT(已绘制覆盖)。两腿摆开
        # 露出的楔形中缝由角色自己的裆部像素补上；运动中的腿永远不会被这层
        # 未旋转的静态列盖住（帧粘连修复的最后一环）。
        pillar_gate = ImageChops.multiply(
            regions["crotch"][0].getchannel("A"), ImageChops.invert(coverage)
        )
        frame.paste(regions["crotch"][0], (0, int(round(dy))), pillar_gate)
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
