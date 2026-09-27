"""Pose-driven animation frames for the 2D character (pure stdlib).

Reuses the exact same palette + vector primitives as the still renderer
(``artgen.character2d``), so every animation frame shares the source image's
style: same outline, same flat fills, same belly/eye treatment. Poses are
derived from the frame phase for idle / walk / run / attack / jump cycles.
"""

import math

from artgen.png import encode_rgba
from artgen.raster import Surface, capsule, ellipse
from artgen.character2d import (
    DESIGN,
    Painter,
    _ear,
    _horn,
    _mix,
    _resolve,
    _scarf,
)

ACTIONS = ("idle", "walk", "run", "attack", "jump")


def _arm_joint(shoulder, angle_deg, length):
    a = math.radians(angle_deg)
    return shoulder[0] + math.sin(a) * length, shoulder[1] + math.cos(a) * length


def _pose(action, phase):
    t = phase * 2.0 * math.pi
    state = {"bob": 0.0, "jump": 0.0, "arm": 0.0, "leg": 0.0, "lean": 0.0,
             "weapon": None, "tuck": 0.0}
    if action == "walk":
        state.update(leg=math.cos(t), arm=-math.cos(t), bob=-abs(math.sin(t)) * 6.0)
    elif action == "run":
        state.update(leg=math.cos(t) * 1.3, arm=-math.cos(t) * 1.3,
                     bob=-abs(math.sin(t)) * 10.0, lean=7.0)
    elif action == "attack":
        state.update(leg=math.sin(t) * 0.4, arm=0.4 + 0.4 * math.sin(t),
                     lean=4.0, weapon=-70.0 + 110.0 * (0.5 + 0.5 * math.sin(t)))
    elif action == "jump":
        state.update(jump=abs(math.sin(math.pi * phase)) * 118.0,
                     leg=0.5, arm=-0.5, tuck=1.0)
    else:  # idle
        state.update(bob=math.sin(t) * 4.0, arm=math.sin(t) * 0.22)
    return state


def _draw_frame(painter, colors, traits, action, phase):
    c = colors
    pose = _pose(action, phase)
    jump = pose["jump"]
    bob = pose["bob"]
    lean = pose["lean"]
    dy = bob - jump
    body_ry = 104.0 if traits["round_body"] else 96.0
    cx = 256.0 + lean

    # ground shadow (fades as the character leaves the ground)
    if jump < 60:
        scale = 1.0 - jump / 160.0
        painter.soft_ellipse(ellipse(256, 500, 150 * scale, 34 * scale), c["dark"], alpha=48)

    # legs
    hip_y = 428.0 + dy
    for side, sign in ((-1, -1), (1, 1)):
        hip = (256.0 + sign * 30, hip_y)
        angle = sign * 10 + pose["leg"] * 30 * -sign
        if pose["tuck"]:
            angle = sign * 18
        foot = _arm_joint(hip, angle, 72.0 - (14.0 if pose["tuck"] else 0.0))
        painter.shape(capsule(hip[0], hip[1], foot[0], foot[1], 32), c["base_dark"], c["outline"], 5)
        painter.shape(ellipse(foot[0], foot[1] + 12, 42, 26), c["base"], c["outline"], 5)

    # torso
    body = 372.0 + dy
    painter.shape(ellipse(cx, body, 112, body_ry), c["base"], c["outline"], 6)
    painter.shape(ellipse(cx, body + 20, 74, body_ry * 0.62), c["belly"], None)
    _scarf(painter, cx, 300.0 + dy, 94, 26, traits)

    # arms
    shoulders = ((cx - 74, 336.0 + dy), (cx + 74, 336.0 + dy))
    for index, (sign, shoulder) in enumerate(((-1, shoulders[0]), (1, shoulders[1]))):
        angle = sign * 16 - pose["arm"] * 34 * sign
        hand = _arm_joint(shoulder, angle, 92.0)
        painter.shape(capsule(shoulder[0], shoulder[1], hand[0], hand[1], 27), c["base"], c["outline"], 5)
        painter.shape(ellipse(hand[0], hand[1], 30, 30), c["belly"], c["outline"], 4)
        if index == 1 and traits["has_weapon"]:
            weapon_angle = pose["weapon"]
            if weapon_angle is None:
                weapon_angle = 60.0
            rad = math.radians(weapon_angle)
            tip = (hand[0] + math.sin(rad) * 118.0, hand[1] - math.cos(rad) * 118.0)
            painter.shape(capsule(hand[0], hand[1], tip[0], tip[1], 11), c["metal"], c["outline"], 4)
            painter.shape(capsule(hand[0], hand[1], tip[0], tip[1], 4),
                          _mix(c["metal"], (255, 255, 255), 0.5), None)
            nx, ny = -(tip[1] - hand[1]), (tip[0] - hand[0])
            length = math.hypot(nx, ny) or 1.0
            nx, ny = nx / length * 26, ny / length * 26
            gx, gy = hand[0] + (tip[0] - hand[0]) * 0.12, hand[1] + (tip[1] - hand[1]) * 0.12
            painter.shape(capsule(gx - nx, gy - ny, gx + nx, gy + ny, 9), c["accent"], c["outline"], 4)

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
    for a, b in (((head_cx - 14, head_cy + 72), (head_cx, head_cy + 80)),
                 ((head_cx, head_cy + 80), (head_cx + 14, head_cy + 72))):
        painter.shape(capsule(a[0], a[1], b[0], b[1], 4), c["dark"], None)


def render_frame_rgba(params, action, phase, size):
    """-> (width, height, RGBA bytes) for one frame."""
    size = max(64, min(1024, int(size)))
    colors, traits = _resolve(params)
    painter = Painter(Surface(size, size), colors, 0.0, 0.0, size / DESIGN)
    _draw_frame(painter, colors, traits, action if action in ACTIONS else "idle", phase)
    return size, size, bytes(painter.s.to_rgba())


def render_frame_png(params, action, phase, size):
    width, height, rgba = render_frame_rgba(params, action, phase, size)
    return encode_rgba(width, height, rgba)


def render_action_frames(params, action, count=12, size=512):
    """-> list of (width, height, RGBA bytes)."""
    count = max(2, min(60, int(count)))
    return [
        render_frame_rgba(params, action, index / count, size)
        for index in range(count)
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
            sheet[dst:dst + frame_w * 4] = rgba[src:src + frame_w * 4]
    return sheet_w, frame_h * rows, bytes(sheet)
