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


def _smoothstep(u):
    """C1 缓动（两端导数为 0）——所有分段曲线的衔接件。"""
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def _rise(u):
    """C1 上升沿 0→1（(1-cos)/2）：蓄力/压缩类前半程曲线。"""
    u = max(0.0, min(1.0, u))
    return 0.5 * (1.0 - math.cos(math.pi * u))


def _bump(u, peak=0.5):
    """C1 平滑单峰窗 0→峰→0，峰位可调（peak=峰出现的窗口比例）。

    用于"膝屈曲/收势"这类必须回到 0 且两端角速度连续的关节曲线：
    sin 窗在窗口边缘有非零导数（触地瞬间角速度突跳），
    cos² 形窗两端导数严格为 0。"""
    if u <= 0.0 or u >= 1.0:
        return 0.0
    p = math.log(0.5) / math.log(max(0.02, min(0.98, peak)))
    return 0.5 * (1.0 - math.cos(2.0 * math.pi * (u ** p)))


def _pose(action, phase, config=None):
    """Pose state for one phase. ``config`` (动作自定义参数) scales/offsets the
    raw curves: bob 起伏、stride 步幅、arm 摆臂、lift 抬脚、lean 前倾、
    lag 手臂滞后（重叠动作）、cycles 每循环运动周期数、turn 转身幅度
    （0~180°，there-and-back 律动，riganim 以水平压缩模拟绕纵轴旋转）。

    ``config["phases"]``（多段编排）: [{"action", "weight", "turn"}, ...]
    按权重把一个循环切成多段，各段独立跑完整原语循环——所有原语段首尾
    都回站立位，天然 C0；turn 跨段线性过渡（含首尾环绕）。

    曲线设计纪律（专业级观感的底线）：
    * 循环动作（idle/walk/run）在 phase 0/1 接缝处 C0+C1 连续——起伏用
      sin²（|sin| 的 V 形尖角是每一步"顿一下"的根源）；
    * 一次性动作（attack/jump）分段曲线在所有段边界 C0 连续、蓄力段
      C1 连续——段间硬切在成片上就是"跳帧"；
    * 膝/肘屈曲峰对齐摆动相窗口（脚离地期间），关节角只朝解剖学允许
      的方向弯（膝/肘恒为屈曲符号，不反关节）；
    * 次级动作（呼吸/重心横移/肩盆反向倾斜）叠加在主循环之上，
      幅度小、频率错开，避免与主节拍共振。"""
    cfg = config or {}
    seq = _sequence_phases(cfg.get("phases"))
    if seq:
        state, turn_deg = _pose_sequence(seq, phase, cfg)
    else:
        state = _pose_single(action, phase, cfg)
        turn_deg = _turn_sway(phase, cfg)
    state["turn"] = turn_deg
    return state


def _sequence_phases(raw):
    """校验 phases 配置 → [{action, weight, turn}]；非法返回 None（回落单原语）。"""

    if not isinstance(raw, list) or len(raw) < 2 or len(raw) > 6:
        return None
    out = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        act = str(item.get("action") or "")
        if act not in ACTIONS:
            return None
        try:
            weight = max(0.2, min(6.0, float(item.get("weight", 1.0))))
        except (TypeError, ValueError):
            return None
        try:
            turn = max(0.0, min(180.0, float(item.get("turn", 0.0) or 0.0)))
        except (TypeError, ValueError):
            turn = 0.0
        out.append({"action": act, "weight": weight, "turn": turn})
    return out


def _pose_sequence(seq, phase, cfg):
    """多段编排：权重切片 + 各段完整原语循环（天然 C0）+ turn 段中心结点
    插值——每段在自己的中心保持本段 turn，过渡跨越段边界（站立段保持
    正脸、转体落在跳跃段内），环绕插值保证接缝闭合。→ (state, turn_deg)。"""

    total = sum(item["weight"] for item in seq)
    centers = []
    acc = 0.0
    for item in seq:
        acc += item["weight"]
        centers.append(acc - item["weight"] / 2.0)
    pos = (phase % 1.0) * total

    acc = 0.0
    index = len(seq) - 1
    local = 1.0
    for i, item in enumerate(seq):
        if pos <= acc + item["weight"] or i == len(seq) - 1:
            index = i
            local = min(1.0, max(0.0, (pos - acc) / item["weight"]))
            break
        acc += item["weight"]
    state = _pose_single(seq[index]["action"], local, cfg)

    # turn：环绕结点插值。pos 在首中心之前 = 头部环绕区（从末中心插向首
    # 中心）；其余按中心 k → 中心 k+1 线性过渡（k 为末段时目标 = 环绕结点
    # c0+total）——turn(phase=1) ≡ turn(phase=0)，接缝闭合
    n = len(seq)
    k = n - 1
    for i in range(n):
        if centers[i] <= pos:
            k = i
    if pos < centers[0]:
        span = (total - centers[n - 1]) + centers[0]
        t = (pos + total - centers[n - 1]) / span
        turn = seq[n - 1]["turn"] + (seq[0]["turn"] - seq[n - 1]["turn"]) * t
    else:
        k_next = (k + 1) % n
        span = (centers[0] + total - centers[k]) if k == n - 1 else (centers[k_next] - centers[k])
        t = (pos - centers[k]) / span
        turn = seq[k]["turn"] + (seq[k_next]["turn"] - seq[k]["turn"]) * t
    return state, turn


def _turn_sway(phase, cfg):
    """单原语路径的转身律动：there-and-back（sin(π·k·phase)，k 取整保证
    循环接缝必回 0°——非整 k 的 sin(2π·cycles·phase) 在接缝会跳角度）。"""

    amplitude = max(0.0, min(180.0, float(cfg.get("turn", 0.0) or 0.0)))
    if amplitude <= 0.5:
        return 0.0
    k = max(1, round(float(cfg.get("cycles", 1.0) or 1.0)))
    return amplitude * math.sin(math.pi * k * phase)


def _pose_single(action, phase, cfg):
    """单一原语的姿态状态（_pose 的主体，phases 分派到此处求值）。"""
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
        "tilt": 0.0,  # 肩线反向倾斜（肩盆反向，次级动作）
    }
    if action == "walk":
        # arms trail the legs slightly (overlapping action); hips sway over
        # the planted foot (weight shift, 2 bobs per cycle like a real gait)
        state.update(
            leg=math.cos(t),
            arm=-math.cos(t - max(0.0, float(cfg.get("lag", 0.45)))),
            bob=-(math.sin(t) ** 2) * 6.0 * float(cfg.get("bob", 1.0)),
            lean=float(cfg.get("lean", 0.0)),
            sway=math.sin(t) * 7.0,
            tilt=math.sin(t) * 2.2,
            lift=(
                max(0.0, math.sin(t)) * 12.0 * float(cfg.get("lift", 1.0)),
                max(0.0, -math.sin(t)) * 12.0 * float(cfg.get("lift", 1.0)),
            ),
        )
        stride = float(cfg.get("stride", 1.0))
        state["leg"] *= stride
        state["arm"] *= float(cfg.get("arm", 1.0))
        # ── 人体运动学关节角（riganim 双骨链消费；矢量路径忽略）──────────
        # 膝二次屈曲：屈曲峰锁定在**摆动相窗口内**（与抬脚同窗，峰在窗口
        # 72% 处 = 收腿末期），支撑期保持 4° 微屈（腿永远不绷直锁死）。
        # cos² 窗保证触地/离地瞬间角速度连续。
        t_mod = t % (2.0 * math.pi)
        swing_l = 0.0 < t_mod < math.pi
        u_l = t_mod / math.pi if swing_l else 0.0
        u_r = ((t_mod + math.pi) % (2.0 * math.pi)) / math.pi
        # 摆动相膝屈 42°（+支撑微屈 4°）：人类步行摆动相膝峰 ~60°，旧值 30°
        # 收腿不足——盲评反馈"腿部动作不自然"的曲线侧因素。峰仍在窗口 72%
        # 处（收腿末期，与抬脚同窗），触地时回到 4° 微屈（不锁死）。
        knee_amp = 42.0 * stride
        state["knee_l"] = -(4.0 + knee_amp * _bump(u_l, peak=0.72)) if swing_l else -4.0
        state["knee_r"] = -(4.0 + knee_amp * _bump(u_r, peak=0.72)) if u_r < 1.0 else -4.0
        # 肘屈曲：基础 ~14°（持物微屈）+ 随摆臂连续加深（正弦调制，
        # 取代半波整流——窗口边缘的速度突跳是肘部"抽动"感的来源）
        arm_lag = max(0.0, float(cfg.get("lag", 0.45)))
        mod = math.sin(t - arm_lag)
        state["elbow_l"] = -(14.0 + 14.0 * 0.5 * (1.0 - mod)) * float(cfg.get("arm", 1.0))
        state["elbow_r"] = -(14.0 + 14.0 * 0.5 * (1.0 + mod)) * float(cfg.get("arm", 1.0))
    elif action == "run":
        state.update(
            leg=math.cos(t) * 1.25,
            arm=-math.cos(t - max(0.0, float(cfg.get("lag", 0.5)))) * 1.25,
            bob=-(math.sin(t) ** 2) * 10.0 * float(cfg.get("bob", 1.0)),
            lean=7.0 + float(cfg.get("lean", 0.0)),
            sway=math.sin(t) * 5.0,
            tilt=math.sin(t) * 1.6,
            lift=(
                max(0.0, math.sin(t)) * 22.0 * float(cfg.get("lift", 1.0)),
                max(0.0, -math.sin(t)) * 22.0 * float(cfg.get("lift", 1.0)),
            ),
        )
        stride = float(cfg.get("stride", 1.0))
        state["leg"] *= stride
        state["arm"] *= float(cfg.get("arm", 1.0))
        t_mod = t % (2.0 * math.pi)
        swing_l = 0.0 < t_mod < math.pi
        u_l = t_mod / math.pi if swing_l else 0.0
        u_r = ((t_mod + math.pi) % (2.0 * math.pi)) / math.pi
        knee_amp = 52.0 * stride
        state["knee_l"] = -(6.0 + knee_amp * _bump(u_l, peak=0.66)) if swing_l else -6.0
        state["knee_r"] = -(6.0 + knee_amp * _bump(u_r, peak=0.66)) if u_r < 1.0 else -6.0
        arm_lag = max(0.0, float(cfg.get("lag", 0.5)))
        mod = math.sin(t - arm_lag)
        state["elbow_l"] = -(30.0 + 18.0 * 0.5 * (1.0 - mod)) * float(cfg.get("arm", 1.0))
        state["elbow_r"] = -(30.0 + 18.0 * 0.5 * (1.0 + mod)) * float(cfg.get("arm", 1.0))
    elif action == "attack":
        # anticipation (hold the coil) -> accelerate into the strike ->
        # impact recoil -> settle back to stance.
        # 分段曲线在全部段边界 C0 连续、蓄力段两端 C1——旧版在 0.3 处
        # 蓄力回零后瞬跳 -0.55、0.8 处 1.07 跳 0.77，成片上是两次"跳帧"。
        if phase < 0.3:
            u = phase / 0.3
            k = -0.55 * _rise(u)
        elif phase < 0.55:
            u = (phase - 0.3) / 0.25
            k = -0.55 + 1.62 * (u * u)  # ease-in：发力段持续加速到命中
        elif phase < 0.8:
            u = (phase - 0.55) / 0.25
            k = 0.92 + 0.15 * math.cos(math.pi * u)  # 命中反冲，平滑回撤
        else:
            u = (phase - 0.8) / 0.2
            k = 0.77 - 0.77 * _smoothstep(u)
        # 命中瞬间重心下沉（重量转移），随挥后恢复
        bob = -3.0 * _bump(min(1.0, phase / 0.62), peak=0.5)
        state.update(
            leg=math.sin(t) * 0.4,
            arm=0.3 - k * 0.25,
            lean=4.0 + k * 10.0 + float(cfg.get("lean", 0.0)),
            weapon=-60.0 + 120.0 * k,
            bob=bob,
        )
    elif action == "jump":
        # crouch (hold the coil) -> ballistic flight (抛物线，重力感) ->
        # landing absorb（落地屈膝缓冲，(1-u)^1.5 平滑回弹到站立）。
        # 旧版蹲底 0→-18、落地 -18→0 硬切 + squat/arm/leg 三处段间跳变。
        if phase < 0.22:
            u = phase / 0.22
            state.update(
                jump=-18.0 * _rise(u),
                arm=0.45 * _rise(u),  # 预摆：手臂后摆蓄力
                squat=1.0,
            )
        elif phase < 0.72:
            u = (phase - 0.22) / 0.5
            tuck = math.sin(math.pi * u)
            if u < 0.4:
                arm = 0.45 - 1.05 * _smoothstep(u / 0.4)  # 手臂前上摆带动起跳
            else:
                arm = -0.6 + 0.5 * _smoothstep((u - 0.4) / 0.6)
            state.update(
                jump=-18.0 + 158.0 * 4.0 * u * (1.0 - u),  # 抛物线弹道
                arm=arm,
                leg=0.5 * tuck,
                tuck=tuck,
                squat=1.0 - tuck,  # 离地展体、空中收腿，全程连续
            )
        else:
            u = (phase - 0.72) / 0.28
            settle = (1.0 - u) ** 1.5
            state.update(
                jump=-18.0 * settle,
                arm=-0.1 * (1.0 - u) - 0.1 * math.sin(math.pi * u) * (1.0 - u),
                leg=0.0,
                squat=settle,  # 落地屈膝缓冲深度
            )
        state["lean"] += float(cfg.get("lean", 0.0))
    else:  # idle: breathing with lazy arm sway trailing the breath
        state.update(
            bob=math.sin(t) * 4.0 * float(cfg.get("bob", 1.0)),
            arm=math.sin(t - max(0.0, float(cfg.get("lag", 0.5))))
            * 0.22
            * float(cfg.get("arm", 1.0)),
            lean=float(cfg.get("lean", 0.0)),
            sway=math.sin(t) * 1.6,  # 站立重心缓慢左右转移（次级动作）
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

    # ground shadow (fades continuously as the character leaves the ground —
    # 旧的 jump<60 硬阈值让阴影在空中段"啪"地消失)
    scale = max(0.0, 1.0 - jump / 160.0)
    if scale > 0.02:
        painter.soft_ellipse(
            ellipse(256, 500, 150 * scale, 34 * scale), c["dark"], alpha=int(48 * scale)
        )

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
