"""Pose-driven animation frames for the 2D character (pure stdlib).

Reuses the exact same palette + vector primitives as the still renderer
(``artgen.character2d``), so every animation frame shares the source image's
style: same outline, same flat fills, same belly/eye treatment. Poses are
derived from the frame phase for idle / walk / run / attack / jump cycles.
"""

import math

from artgen.character2d import (
    DESIGN,
    Painter,
    _ear,
    _horn,
    _mix,
    _resolve,
    _scarf,
)
from artgen.png import encode_rgba
from artgen.raster import Surface, capsule, ellipse

ACTIONS = ("idle", "walk", "run", "attack", "jump")


def _arm_joint(shoulder, angle_deg, length):
    a = math.radians(angle_deg)
    return shoulder[0] + math.sin(a) * length, shoulder[1] + math.cos(a) * length


def _two_bone(root, target, l1, l2, bend):
    """Middle-joint position of a two-segment limb reaching from ``root`` to
    ``target`` (standard IK circle intersection). ``bend`` (+1/-1) picks which
    way the joint points, giving elbows/knees a fixed, anatomically stable
    bend direction across the whole cycle."""
    dx, dy = target[0] - root[0], target[1] - root[1]
    d = math.hypot(dx, dy)
    if d < 1e-3:
        return root[0], root[1] - l1
    d = min(d, l1 + l2 - 1e-3)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    ux, uy = dx / d, dy / d
    mx, my = root[0] + ux * a, root[1] + uy * a
    return mx - uy * h * bend, my + ux * h * bend


def _pose(action, phase, config=None):
    """Pose state for one phase. ``config`` (动作自定义参数) scales/offsets the
    raw curves: bob 起伏、stride 步幅、arm 摆臂、lift 抬脚、lean 前倾、
    lag 手臂滞后（重叠动作）、cycles 每循环运动周期数。"""
    cfg = config or {}
    cycles = max(0.25, min(4.0, float(cfg.get("cycles", 1.0))))
    cyclic = action in ("idle", "walk", "run")
    t = phase * 2.0 * math.pi * (cycles if cyclic else 1.0)
    state = {
        "bob": 0.0,
        "jump": 0.0,
        "arm": 0.0,
        "leg": 0.0,
        "lean": 0.0,
        "weapon": None,
        "tuck": 0.0,
        "lift": (0.0, 0.0),
        "squat": 0.0,
        "sway": 0.0,
    }
    if action == "walk":
        # arms trail the legs slightly (overlapping action); hips sway over
        # the planted foot (weight shift, 2 bobs per cycle like a real gait)
        state.update(
            leg=math.cos(t),
            arm=-math.cos(t - max(0.0, float(cfg.get("lag", 0.45)))),
            bob=-abs(math.sin(t)) * 6.0 * float(cfg.get("bob", 1.0)),
            lean=float(cfg.get("lean", 0.0)),
            sway=math.sin(t) * 7.0,
            lift=(
                max(0.0, math.sin(t)) * 12.0 * float(cfg.get("lift", 1.0)),
                max(0.0, -math.sin(t)) * 12.0 * float(cfg.get("lift", 1.0)),
            ),
        )
        stride = float(cfg.get("stride", 1.0))
        state["leg"] *= stride
        state["arm"] *= float(cfg.get("arm", 1.0))
        # ── 人体运动学关节角（riganim 双骨链消费；矢量路径忽略）──────────
        # 膝二次屈曲：摆动相中后期收腿屈膝（峰 ~30°），支撑相反相伸直。
        # 摆动相中点在 cos 极值之后（t≈1.4π），故曲线用 sin(t-0.4π) 取峰。
        swing_l = max(0.0, math.sin(t - 0.4 * math.pi))
        state["knee_l"] = -(swing_l ** 1.2) * 30.0 * stride
        state["knee_r"] = -((max(0.0, math.sin(t - 0.4 * math.pi + math.pi))) ** 1.2) * 30.0 * stride
        # 肘屈曲：基础 ~14°（持物微屈）+ 前摆加深，与上臂摆动相位耦合
        arm_lag = max(0.0, float(cfg.get("lag", 0.45)))
        state["elbow_l"] = -(14.0 + 14.0 * max(0.0, -math.sin(t - arm_lag))) * float(cfg.get("arm", 1.0))
        state["elbow_r"] = -(14.0 + 14.0 * max(0.0, math.sin(t - arm_lag))) * float(cfg.get("arm", 1.0))
    elif action == "run":
        state.update(
            leg=math.cos(t) * 1.25,
            arm=-math.cos(t - max(0.0, float(cfg.get("lag", 0.5)))) * 1.25,
            bob=-abs(math.sin(t)) * 10.0 * float(cfg.get("bob", 1.0)),
            lean=7.0 + float(cfg.get("lean", 0.0)),
            sway=math.sin(t) * 5.0,
            lift=(
                max(0.0, math.sin(t)) * 22.0 * float(cfg.get("lift", 1.0)),
                max(0.0, -math.sin(t)) * 22.0 * float(cfg.get("lift", 1.0)),
            ),
        )
        stride = float(cfg.get("stride", 1.0))
        state["leg"] *= stride
        state["arm"] *= float(cfg.get("arm", 1.0))
        swing_l = max(0.0, math.sin(t - 0.4 * math.pi))
        state["knee_l"] = -(swing_l ** 1.1) * 52.0 * stride
        state["knee_r"] = -((max(0.0, math.sin(t - 0.4 * math.pi + math.pi))) ** 1.1) * 52.0 * stride
        arm_lag = max(0.0, float(cfg.get("lag", 0.5)))
        state["elbow_l"] = -(30.0 + 18.0 * max(0.0, -math.sin(t - arm_lag))) * float(cfg.get("arm", 1.0))
        state["elbow_r"] = -(30.0 + 18.0 * max(0.0, math.sin(t - arm_lag))) * float(cfg.get("arm", 1.0))
    elif action == "attack":
        # anticipation (wind-up) -> fast strike -> follow-through -> recover
        # (one-shot action: never time-scaled by cycles)
        if phase < 0.3:
            u = phase / 0.3
            k = -0.55 * math.sin(math.pi * u)
        elif phase < 0.55:
            u = (phase - 0.3) / 0.25
            k = -0.55 + 1.62 * (u * u * (3 - 2 * u))
        elif phase < 0.8:
            u = (phase - 0.55) / 0.25
            k = 1.07 - 0.3 * math.sin(math.pi * u)
        else:
            u = (phase - 0.8) / 0.2
            k = 0.77 - 0.77 * (u * u * (3 - 2 * u))
        state.update(
            leg=math.sin(t) * 0.4,
            arm=0.3 - k * 0.25,
            lean=4.0 + k * 10.0 + float(cfg.get("lean", 0.0)),
            weapon=-60.0 + 120.0 * k,
        )
    elif action == "jump":
        if phase < 0.22:
            # anticipation: crouch, arms swing back
            u = phase / 0.22
            state.update(jump=-18.0 * math.sin(math.pi * u), arm=0.5 * u, squat=1.0)
        elif phase < 0.72:
            u = (phase - 0.22) / 0.5
            state.update(
                jump=-18.0 + 140.0 * math.sin(math.pi * u),
                arm=-0.6,
                leg=0.5,
                tuck=math.sin(math.pi * u),
            )
        else:
            # landing: absorb the impact with a decaying squat
            u = (phase - 0.72) / 0.28
            state.update(
                jump=-14.0 * (1.0 - u) * math.sin(math.pi * min(1.0, u * 1.6)),
                arm=-0.3 * (1.0 - u),
                squat=1.0 - u,
            )
        state["lean"] += float(cfg.get("lean", 0.0))
    else:  # idle: breathing with lazy arm sway trailing the breath
        state.update(
            bob=math.sin(t) * 4.0 * float(cfg.get("bob", 1.0)),
            arm=math.sin(t - max(0.0, float(cfg.get("lag", 0.5))))
            * 0.22
            * float(cfg.get("arm", 1.0)),
            lean=float(cfg.get("lean", 0.0)),
        )
    return state


def _draw_frame(painter, colors, traits, action, phase, config=None):
    c = colors
    pose = _pose(action, phase, config)
    jump = pose["jump"]
    bob = pose["bob"]
    lean = pose["lean"]
    dy = bob - jump
    body_ry = 104.0 if traits["round_body"] else 96.0
    sway = pose.get("sway", 0.0)
    cx = 256.0 + lean + sway

    # ground shadow (fades as the character leaves the ground)
    if jump < 60:
        scale = 1.0 - jump / 160.0
        painter.soft_ellipse(ellipse(256, 500, 150 * scale, 34 * scale), c["dark"], alpha=48)

    # legs: hip -> knee -> ankle (two-bone), feet lift alternately when stepping
    hip_y = 428.0 + dy + pose["squat"] * 8.0
    for side, (sign, lift) in enumerate(((-1, pose["lift"][0]), (1, pose["lift"][1]))):
        hip = (256.0 + sign * 30 + sway * 0.8, hip_y)
        angle = sign * 8 + pose["leg"] * 16 * -sign
        reach = 76.0
        if pose["tuck"]:
            angle = sign * 20
            reach = 58.0
        foot = _arm_joint(hip, angle, reach)
        foot = (foot[0], foot[1] - lift)
        knee = _two_bone(hip, foot, 40.0, 40.0, bend=sign * (1.0 + pose["tuck"] * 0.6))
        painter.shape(
            capsule(hip[0], hip[1], knee[0], knee[1], 30), c["base_dark"], c["outline"], 5
        )
        painter.shape(
            capsule(knee[0], knee[1], foot[0], foot[1], 22), c["base_dark"], c["outline"], 5
        )
        painter.shape(ellipse(foot[0], foot[1] + 10, 42, 24), c["base"], c["outline"], 5)

    # torso
    body = 372.0 + dy + pose["squat"] * 8.0
    painter.shape(ellipse(cx, body, 112, body_ry), c["base"], c["outline"], 6)
    painter.shape(ellipse(cx, body + 20, 74, body_ry * 0.62), c["belly"], None)
    _scarf(painter, cx, 300.0 + dy + pose["squat"] * 8.0, 94, 26, traits)

    # arms: shoulder -> elbow -> wrist (two-bone), elbows bend outward
    shoulders = (
        (cx - 74, 336.0 + dy + pose["squat"] * 8.0),
        (cx + 74, 336.0 + dy + pose["squat"] * 8.0),
    )
    for index, (sign, shoulder) in enumerate(((-1, shoulders[0]), (1, shoulders[1]))):
        angle = sign * 16 - pose["arm"] * 34 * sign
        hand = _arm_joint(shoulder, angle, 94.0)
        elbow = _two_bone(shoulder, hand, 48.0, 50.0, bend=-sign)
        painter.shape(
            capsule(shoulder[0], shoulder[1], elbow[0], elbow[1], 24), c["base"], c["outline"], 5
        )
        painter.shape(capsule(elbow[0], elbow[1], hand[0], hand[1], 19), c["base"], c["outline"], 5)
        painter.shape(ellipse(hand[0], hand[1], 28, 28), c["belly"], c["outline"], 4)
        if index == 1 and traits["has_weapon"]:
            weapon_angle = pose["weapon"]
            if weapon_angle is None:
                weapon_angle = 60.0
            rad = math.radians(weapon_angle)
            tip = (hand[0] + math.sin(rad) * 118.0, hand[1] - math.cos(rad) * 118.0)
            painter.shape(
                capsule(hand[0], hand[1], tip[0], tip[1], 11), c["metal"], c["outline"], 4
            )
            painter.shape(
                capsule(hand[0], hand[1], tip[0], tip[1], 4),
                _mix(c["metal"], (255, 255, 255), 0.5),
                None,
            )
            nx, ny = -(tip[1] - hand[1]), (tip[0] - hand[0])
            length = math.hypot(nx, ny) or 1.0
            nx, ny = nx / length * 26, ny / length * 26
            gx, gy = hand[0] + (tip[0] - hand[0]) * 0.12, hand[1] + (tip[1] - hand[1]) * 0.12
            painter.shape(
                capsule(gx - nx, gy - ny, gx + nx, gy + ny, 9), c["accent"], c["outline"], 4
            )

    # ears + horns + head
    head_cx = cx
    head_cy = 196.0 + dy * 0.9
    _ear(painter, head_cx - 106, head_cy - 68, -1, traits)
    _ear(painter, head_cx + 106, head_cy - 68, 1, traits)
    _horn(painter, head_cx - 60, head_cy - 104, -1, traits)
    _horn(painter, head_cx + 60, head_cy - 104, 1, traits)
    painter.shape(ellipse(head_cx, head_cy, 140, 134), c["base"], c["outline"], 6)
    painter.shape(ellipse(head_cx, head_cy + 62, 86, 62), c["muzzle"], c["outline"], 5)
    painter.shape(ellipse(head_cx, head_cy + 32, 26, 18), c["dark"], None)
    for eye_x in (head_cx - 52, head_cx + 52):
        painter.shape(ellipse(eye_x, head_cy - 14, 22, 29), c["dark"], None)
        painter.shape(ellipse(eye_x - 7, head_cy - 24, 8, 9), c["white"], None)
    painter.soft_ellipse(ellipse(head_cx - 88, head_cy + 36, 30, 17), c["blush"], alpha=150)
    painter.soft_ellipse(ellipse(head_cx + 88, head_cy + 36, 30, 17), c["blush"], alpha=150)
    for a, b in (
        ((head_cx - 14, head_cy + 72), (head_cx, head_cy + 80)),
        ((head_cx, head_cy + 80), (head_cx + 14, head_cy + 72)),
    ):
        painter.shape(capsule(a[0], a[1], b[0], b[1], 4), c["dark"], None)


def render_frame_rgba(params, action, phase, size, config=None):
    """-> (width, height, RGBA bytes) for one frame."""
    size = max(64, min(1024, int(size)))
    colors, traits = _resolve(params)
    painter = Painter(Surface(size, size), colors, 0.0, 0.0, size / DESIGN)
    _draw_frame(painter, colors, traits, action if action in ACTIONS else "idle", phase, config)
    return size, size, bytes(painter.s.to_rgba())


def render_frame_png(params, action, phase, size, config=None):
    width, height, rgba = render_frame_rgba(params, action, phase, size, config)
    return encode_rgba(width, height, rgba)


def render_action_frames(params, action, count=12, size=512, config=None):
    """-> list of (width, height, RGBA bytes)."""
    count = max(2, min(60, int(count)))
    return [
        render_frame_rgba(params, action, index / count, size, config) for index in range(count)
    ]


def render_sprite_sheet(params, action, count, size, columns=None):
    """Frames packed into a strip -> (width, height, RGBA bytes)."""
    return pack_sheet(render_action_frames(params, action, count, size), columns)


def pack_sheet(frames, columns=None):
    """Pack already-rendered (w,h,RGBA) frames into a grid sheet."""
    frame_w, frame_h = frames[0][0], frames[0][1]
    columns = columns or len(frames)
    rows = (len(frames) + columns - 1) // columns
    sheet_w = frame_w * columns
    sheet = bytearray(sheet_w * frame_h * rows * 4)
    for index, (_, _, rgba) in enumerate(frames):
        gx = (index % columns) * frame_w
        gy = (index // columns) * frame_h
        for y in range(frame_h):
            src = y * frame_w * 4
            dst = ((gy + y) * sheet_w + gx) * 4
            sheet[dst : dst + frame_w * 4] = rgba[src : src + frame_w * 4]
    return sheet_w, frame_h * rows, bytes(sheet)
