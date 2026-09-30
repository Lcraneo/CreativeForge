"""Side-view (2D 平台游戏) walk/run gait — the dedicated locomotion system.

正面行走天然锁不住"哪条腿在前"(Windup 同款结论: 步态位移必须锁连续性),横版
侧视角是行业标准解法。这里用一个参数化侧视骨架实现经典步态循环:

    每条腿一个步态相位 (相差半周期):
      支撑期 [0, 0.5): 脚掌贴地, 从身前滑到身后 (重心压过支撑脚)
      摆动期 [0.5, 1): 脚掌离地, 沿平滑弧线摆回身前, 抬脚高度居中峰值
    髋关节用两段式 IK 反解膝/肘; 躯干以 2 倍步频起伏 (每步一次重心下沉),
    前倾角随速度增大; 双臂反相摆动并滞后 (重叠动作)。

帧以脚底为锚 (ground-anchored, 参照 Windup 的 ANCHOR_FOOT), 站立高度恒定。
"""

import math

from artgen.anim import _two_bone
from artgen.character2d import DESIGN, Painter, _mix, _resolve, _scarf
from artgen.raster import Surface, capsule, ellipse

GAIT = ("walk", "run")


def _foot_path(phase, stride, lift):
    """-> (dx, dy) of one foot relative to the point under the hip.

    phase 0: front contact → 0.25: mid-stance → 0.5: toe-off →
    0.5..1: swing arc back to front contact (smoothstep + sine lift)."""
    if phase < 0.5:
        u = phase / 0.5
        return stride * (0.5 - u), 0.0
    u = (phase - 0.5) / 0.5
    eased = u * u * (3 - 2 * u)
    return -stride * 0.5 + stride * eased, -lift * math.sin(math.pi * u)


def _gait_params(action, config):
    cfg = config or {}
    base = {
        "walk": {"stride": 96.0, "lift": 34.0, "lean": 6.0, "bob": 8.0, "arm": 26.0},
        "run": {"stride": 148.0, "lift": 58.0, "lean": 14.0, "bob": 12.0, "arm": 40.0},
    }[action if action in GAIT else "walk"]
    return {
        "stride": base["stride"] * float(cfg.get("stride", 1.0)),
        "lift": base["lift"] * float(cfg.get("lift", 1.0)),
        "lean": base["lean"] + float(cfg.get("lean", 0.0)),
        "bob": base["bob"] * float(cfg.get("bob", 1.0)),
        "arm": base["arm"] * float(cfg.get("arm", 1.0)),
        "lag": max(0.0, min(1.5, float(cfg.get("lag", 0.35)))),
    }


def _side_frame(painter, colors, traits, action, phase, config=None):
    """One side-view frame, character facing right, feet anchored on ground."""
    c = colors
    p = _gait_params(action, config)
    lean_rad = math.radians(p["lean"])

    ground = 500.0
    hip_x, hip_y = 256.0, 402.0
    # vertical bob at 2x stride frequency: the body dips at every weight pass
    bob = -abs(math.sin(2.0 * math.pi * phase)) * p["bob"]
    hip = (hip_x, hip_y + bob)
    chest = (hip_x + math.sin(lean_rad) * 84.0, hip_y + bob - math.cos(lean_rad) * 84.0)
    head_c = (chest[0] + 34.0, chest[1] - 74.0 + math.sin(2.0 * math.pi * phase + 0.9) * 3.0)

    # ground shadow
    painter.soft_ellipse(ellipse(256.0, ground + 8.0, 140.0, 26.0), c["dark"], alpha=42)

    def limb(root, target, l1, l2, bend, w1, w2, fill):
        mid = _two_bone(root, target, l1, l2, bend)
        painter.shape(capsule(root[0], root[1], mid[0], mid[1], w1), fill, c["outline"], 5)
        painter.shape(capsule(mid[0], mid[1], target[0], target[1], w2), fill, c["outline"], 5)
        return mid

    # ---- far leg + far arm (behind the body, darker shade) ----------------
    far_p = (phase + 0.5) % 1.0
    fdx, fdy = _foot_path(far_p, p["stride"], p["lift"])
    far_foot = (hip[0] + fdx, ground - fdy)
    limb(hip, far_foot, 54.0, 54.0, bend=1.0, w1=26, w2=19, fill=c["base_dark"])
    painter.shape(
        ellipse(far_foot[0] + 8.0, far_foot[1] - 6.0, 36, 20), c["base_dark"], c["outline"], 4
    )
    far_shoulder = (chest[0] - 12.0, chest[1] + 18.0)
    far_hand = (
        far_shoulder[0] - p["arm"] * math.cos(2.0 * math.pi * phase) * 0.9 - 6.0,
        far_shoulder[1] + 66.0 + p["arm"] * 0.35 * math.sin(2.0 * math.pi * phase),
    )
    limb(far_shoulder, far_hand, 40.0, 42.0, bend=1.0, w1=19, w2=15, fill=c["base_dark"])
    painter.shape(ellipse(far_hand[0], far_hand[1], 20, 20), c["base_dark"], c["outline"], 3)

    # ---- tail (secondary motion, trails the body with lag) ----------------
    tail_phase = 2.0 * math.pi * phase + math.pi * 0.85
    tail_root = (hip[0] - 58.0, hip[1] - 6.0)
    tail_mid = (tail_root[0] - 46.0, tail_root[1] - 26.0 + math.sin(tail_phase) * 9.0)
    tail_tip = (tail_mid[0] - 34.0, tail_mid[1] - 18.0 + math.sin(tail_phase + 0.7) * 12.0)
    painter.shape(
        capsule(tail_root[0], tail_root[1], tail_mid[0], tail_mid[1], 16),
        c["base"],
        c["outline"],
        4,
    )
    painter.shape(
        capsule(tail_mid[0], tail_mid[1], tail_tip[0], tail_tip[1], 9), c["base"], c["outline"], 4
    )
    painter.shape(ellipse(tail_tip[0], tail_tip[1], 17, 17), c["belly"], c["outline"], 3)

    # ---- torso: capsule hip -> chest, carrying the lean --------------------
    painter.shape(
        capsule(hip[0], hip[1] - 10.0, chest[0], chest[1], 46), c["base"], c["outline"], 6
    )
    painter.shape(
        ellipse((hip[0] + chest[0]) / 2 + 12.0, (hip[1] + chest[1]) / 2, 42, 52), c["belly"], None
    )
    _scarf(painter, chest[0] - 6.0, chest[1] - 6.0, 74, 22, traits)

    # ---- head (profile: muzzle to the right) -------------------------------
    painter.shape(ellipse(head_c[0], head_c[1], 64, 58), c["base"], c["outline"], 6)
    painter.shape(ellipse(head_c[0] + 44.0, head_c[1] + 16.0, 30, 22), c["base"], c["outline"], 5)
    painter.shape(ellipse(head_c[0] + 62.0, head_c[1] + 13.0, 12, 9), c["dark"], None)
    painter.shape(ellipse(head_c[0] + 18.0, head_c[1] - 8.0, 9, 12), c["dark"], None)
    painter.shape(ellipse(head_c[0] + 21.0, head_c[1] - 11.0, 3.5, 4.5), c["white"], None)
    _side_ear(painter, head_c, c)
    if traits.get("has_horn"):
        painter.shape(
            capsule(head_c[0] - 14.0, head_c[1] - 54.0, head_c[0] - 30.0, head_c[1] - 84.0, 7),
            c["accent"],
            c["outline"],
            3,
        )

    # ---- near arm (in front of torso, opposite swing to near leg) ----------
    near_shoulder = (chest[0] + 6.0, chest[1] + 14.0)
    near_hand = (
        near_shoulder[0] + p["arm"] * math.cos(2.0 * math.pi * phase) * 0.9,
        near_shoulder[1] + 64.0 - p["arm"] * 0.35 * math.sin(2.0 * math.pi * phase),
    )
    limb(near_shoulder, near_hand, 42.0, 44.0, bend=-1.0, w1=21, w2=16, fill=c["base"])
    painter.shape(ellipse(near_hand[0], near_hand[1], 21, 21), c["belly"], c["outline"], 3)
    if traits.get("has_weapon"):
        rad = math.radians(56.0)
        tip = (near_hand[0] + math.cos(rad) * 108.0, near_hand[1] - math.sin(rad) * 108.0)
        painter.shape(
            capsule(near_hand[0], near_hand[1], tip[0], tip[1], 9), c["metal"], c["outline"], 4
        )
        painter.shape(
            capsule(near_hand[0], near_hand[1], tip[0], tip[1], 3.5),
            _mix(c["metal"], (255, 255, 255), 0.5),
            None,
        )

    # ---- near leg (drawn last, in front of the torso) ----------------------
    ndx, ndy = _foot_path(phase, p["stride"], p["lift"])
    near_foot = (hip[0] + ndx, ground - ndy)
    limb(hip, near_foot, 54.0, 54.0, bend=1.0, w1=29, w2=21, fill=c["base"])
    painter.shape(
        ellipse(near_foot[0] + 8.0, near_foot[1] - 6.0, 38, 21), c["base"], c["outline"], 5
    )


def _side_ear(painter, head_c, c):
    painter.shape(ellipse(head_c[0] - 40.0, head_c[1] - 44.0, 14, 20), c["base"], c["outline"], 4)
    painter.shape(ellipse(head_c[0] + 16.0, head_c[1] - 50.0, 13, 18), c["base"], c["outline"], 4)


def render_side_frame_rgba(params, action, phase, size, config=None):
    """-> (width, height, RGBA bytes) of one side-view gait frame."""
    size = max(64, min(1024, int(size)))
    colors, traits = _resolve(params)
    painter = Painter(Surface(size, size), colors, 0.0, 0.0, size / DESIGN)
    _side_frame(painter, colors, traits, action if action in GAIT else "walk", phase, config)
    return size, size, bytes(painter.s.to_rgba())


def render_side_frames(params, action, count=12, size=512, config=None):
    """-> list of (width, height, RGBA bytes); one full gait cycle."""
    count = max(2, min(60, int(count)))
    return [
        render_side_frame_rgba(params, action, index / count, size, config)
        for index in range(count)
    ]
