"""多段编排（phases）与转身（turn）原语契约测试（离线、确定性）。

背景：「起舞→飞行」事故的根治验证——
  * jump 慢周期大弧线的悬浮观感由 interpret 钳制拦截（routes 层，此处测引擎侧兜底）
  * 「站立→旋转→跳跃→舞蹈」由 phases 序列表达，逐段跑完整原语循环（天然 C0）
  * turn 为 there-and-back 转身律动，循环接缝必回 0°；riganim 以水平压缩渲染

Run: python tests/test_motion_sequence.py
"""

import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))
    print(
        f"[{'PASS' if condition else 'FAIL'}] {name}"
        + (f" -- {detail}" if detail and not condition else "")
    )


def test_pose_sequence():
    from artgen.anim import _pose

    cfg = {
        "phases": [
            {"action": "idle", "weight": 2, "turn": 0},
            {"action": "jump", "weight": 1, "turn": 90},
            {"action": "idle", "weight": 1, "turn": 30},
        ],
        "cycles": 1,
    }
    total = 4.0
    # 段切分：phase 0.1 → idle 段（无跳跃位移），phase 0.55 → jump 段（弹道>0）
    idle_state = _pose("idle", 0.1 / total, cfg)
    check("seq: 第一段为 idle（无弹道）", abs(idle_state["jump"]) < 1e-6)
    jump_state = _pose("idle", (2.0 + 0.5) / total, cfg)
    check("seq: 第二段进入 jump 弹道", jump_state["jump"] > 40.0, str(jump_state["jump"]))

    # turn 中心结点：站立段前半保持 0°（正脸），跨边界向跳跃段 90° 过渡
    hold = _pose("idle", 0.1 / total, cfg)
    check("seq: 站立段前半保持正脸（turn≈0）", abs(hold["turn"]) < 25.0, str(hold["turn"]))
    near_edge = _pose("idle", (2.0 - 0.04) / total, cfg)
    check("seq: 段尾向跳跃段 turn 过渡", 30.0 < near_edge["turn"] < 90.0, str(near_edge["turn"]))

    # C0 接缝：所有段边界两侧状态差有界（各原语段首尾回站立位）
    max_jump_delta = 0.0
    for boundary in (2.0 / total, 3.0 / total):
        eps = 1.0 / 480.0
        a = _pose("idle", boundary - eps, cfg)
        b = _pose("idle", boundary + eps, cfg)
        max_jump_delta = max(
            max_jump_delta, abs(a["jump"] - b["jump"]), abs(a["bob"] - b["bob"])
        )
    check("seq: 段边界 C0（bob/jump 跳变 < 6px）", max_jump_delta < 6.0, str(max_jump_delta))

    # 循环闭合：phase 0 与 phase 1-ε 状态一致
    head = _pose("idle", 0.0, cfg)
    tail = _pose("idle", 1.0 - 1.0 / 480.0, cfg)
    check(
        "seq: 循环闭合（bob/jump/turn 接缝一致）",
        abs(head["bob"] - tail["bob"]) < 1.0
        and abs(head["jump"] - tail["jump"]) < 1.0
        and abs(head["turn"] - tail["turn"]) < 1.0,
    )

    # 非法 phases 回落单原语
    bad = _pose("walk", 0.3, {"phases": [{"action": "fly", "weight": 1}]})
    plain = _pose("walk", 0.3, {})
    check("seq: 非法 phases 回落单原语", abs(bad["leg"] - plain["leg"]) < 1e-9)


def test_turn_curve():
    from artgen.anim import _pose

    cfg = {"turn": 90.0, "cycles": 1}
    check("turn: phase 0 回 0°", _pose("idle", 0.0, cfg)["turn"] == 0.0)
    check("turn: 相位 0.5 峰值 ±90°", abs(abs(_pose("idle", 0.5, cfg)["turn"]) - 90.0) < 1e-6)
    check("turn: 循环接缝回 0°", abs(_pose("idle", 1.0 - 1e-9, cfg)["turn"]) < 1e-6)
    # 非整 cycles 也必须接缝回 0（there-and-back 设计的意义）
    cfg2 = {"turn": 70.0, "cycles": 1.5}
    check("turn: 非整周期接缝仍回 0°", abs(_pose("idle", 1.0 - 1e-9, cfg2)["turn"]) < 1e-6)
    check("turn: 默认关闭", _pose("walk", 0.4, {})["turn"] == 0.0)


def test_turn_render():
    """riganim 渲染层：turn 峰值帧主体显著变窄（水平压缩生效）且循环闭合。"""

    from PIL import Image

    from artgen.riganim import animate_rigged

    # 合成一张不透明底的人形色块（与 run_animation_tests 同思路）
    from PIL import ImageDraw

    size = 384
    image = Image.new("RGB", (size, size), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 60, 234, 130), fill=(90, 90, 90))  # 头
    draw.rectangle((140, 130, 244, 280), fill=(60, 120, 200))  # 躯干
    draw.rectangle((150, 280, 190, 350), fill=(60, 120, 200))  # 左腿
    draw.rectangle((194, 280, 234, 350), fill=(60, 120, 200))  # 右腿
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()

    plain, _, _, _ = animate_rigged(payload, "idle", 13, size, config={"cycles": 1})
    turned, _, _, _ = animate_rigged(
        payload, "idle", 13, size, config={"cycles": 1, "turn": 90.0}
    )

    def subject_width(frame):
        img = Image.frombytes("RGBA", (frame[0], frame[1]), bytes(frame[2]))
        pixels = img.load()
        xs = [
            x
            for y in range(0, frame[1], 4)
            for x in range(0, frame[0], 2)
            if pixels[x, y][:3] != (240, 240, 240)
        ]
        return (max(xs) - min(xs)) if xs else 0

    # turn 峰值在相位 0.25/0.75（sin 峰），取该帧对比
    peak = 3  # 13 帧的第 4 帧 phase≈0.25
    w_plain = subject_width(plain[peak])
    w_turn = subject_width(turned[peak])
    check("turn: 峰值帧主体显著变窄", w_turn < w_plain * 0.75, f"{w_plain} -> {w_turn}")
    # 帧循环只渲染 [0, 1) 相位，接缝闭合由 pose 层检查覆盖；此处验证
    # turn=0 的首帧与无 turn 路径逐字节一致（alpha over 重构零副作用）
    check("turn: 关闭时与原路径逐字节一致", bytes(turned[0][2]) == bytes(plain[0][2]))
    check("turn: 峰值帧确实发生变形", bytes(turned[peak][2]) != bytes(plain[peak][2]))


import io  # noqa: E402  (test_turn_render 使用)


def main() -> int:
    test_pose_sequence()
    test_turn_curve()
    test_turn_render()
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
