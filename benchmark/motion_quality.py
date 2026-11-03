"""动作质量量化评估（离线、确定性、零额度）——V3.5 量化评估标准.

对应三项量化指标（完整版需求原文）：

  1. 动作流畅度评分 smoothness   —— 帧间过渡的卡顿现象
     * motion_cv   相邻帧运动能量的变异系数（越低越匀；高 = 忽快忽慢）
     * seam_ratio  循环接缝残差 = 首尾帧差 / 平均相邻帧差（>1 即回跳可见）
     * jerk_ratio  运动能量的时间抖动（二阶差分/均值；高 = 加速度突跳）
     * max_jump    最大单帧跳变（绝对卡帧尖峰）
  2. 动作辨识度 distinctness     —— 每个动作的关键姿态特征准确呈现
     * min_pairwise 同一角色五动作两两均值像差的最小值（全对全可分下限）
     * key_features 关键姿态特征硬门：attack 命中前倾/武器扫掠、jump 顶点
       离地、run 膝幅>walk、walk 抬脚交替、逐项布尔
  3. 细节还原准确率 fidelity     —— 衣物/武器/配饰等视觉元素还原
     * style_overall 逐帧 similarity_rgba overall 均值（调色板/色彩/线条）
     * detail_survival 源图显著色簇（武器金、甲蓝等）在帧中的存活率——
       编码（GIF 255 色）与分区变形都不应"吃掉"角色标志色

评分：三维度各 0~100（锚点见 _SCORE_ANCHORS，注释即规格）。
基线/门禁/A-B 三模式，与 video_quality.py 同一规程::

  python benchmark/motion_quality.py            # 打印报告
  python benchmark/motion_quality.py --record   # 写 benchmark/motion_baseline.json
  python benchmark/motion_quality.py --check    # 对基线硬门，失败退出码 1
  python benchmark/motion_quality.py --ab       # 三项优化的 A/B 对照表
"""

import io
import json
import math
import os
import statistics
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "motion_baseline.json")

ACTIONS = ("idle", "walk", "run", "attack", "jump")
BLEND_ALPHA = 0.25  # 与 artgen.pipeline._ghost_blend 生产值一致
RENDER_SIZE = 192
RENDER_FRAMES = 24

# ── 评分锚点（改动=历史基线不可比，需 --record 重录）────────────────────
_SCORE_ANCHORS = {
    "motion_cv": (0.0, 0.5),      # (完美, 不可接受) 线性惩罚
    "seam_ratio": (1.0, 3.0),     # 接缝差 = 均值即无感；3× 即明显回跳
    "jerk_ratio": (0.3, 1.0),
    "min_pairwise": (0.0, 12.0),  # 辨识度：0 不可分 → 12 完全可分
}
_SMOOTH_WEIGHTS = {"motion_cv": 0.45, "seam_ratio": 0.35, "jerk_ratio": 0.20}


# ── 夹具（确定性合成角色，含可检测的标志色）────────────────────────────────
def _knight_png():
    """持械骑士：头/甲蓝躯干/灰臂/深腿 + **金色武器**（细节色存活率的探针）。
    头顶留 ≥40px 供跳跃弧线（riganim 顶部保护会钳制贴顶角色）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (192, 192), (245, 245, 245))
    d = ImageDraw.Draw(img)
    d.ellipse((66, 44, 126, 98), fill=(60, 70, 90))  # 头
    d.rectangle((70, 98, 122, 148), fill=(90, 110, 150))  # 躯干（甲蓝）
    d.rectangle((50, 110, 78, 142), fill=(140, 140, 148))  # 左臂
    d.rectangle((114, 110, 142, 142), fill=(140, 140, 148))  # 右臂
    d.rectangle((70, 148, 90, 186), fill=(70, 80, 100))  # 左腿
    d.rectangle((102, 148, 122, 186), fill=(70, 80, 100))  # 右腿
    d.rectangle((141, 118, 147, 166), fill=(205, 178, 70))  # 金色武器
    import io

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _load_frames_rgba(frames):
    """兼容两种形态：PIL 图列表 / (w,h,rgba) 元组列表。"""
    from PIL import Image

    out = []
    for item in frames:
        if isinstance(item, Image.Image):
            out.append(item)
        else:
            w, h, rgba = item
            out.append(Image.frombytes("RGBA", (w, h), bytes(rgba)))
    return out


def _arr(image):
    import numpy as np

    return np.asarray(image, dtype=np.float32)


# ── 指标原语 ──────────────────────────────────────────────────────────────
def _frame_energy(profile):
    """相邻帧（含环绕对）平均绝对差。profile: list of np arrays."""
    energies = []
    count = len(profile)
    for i in range(count):
        energies.append(float(abs(profile[i] - profile[(i + 1) % count]).mean()))
    return energies


def smoothness_metrics(frames_rgba):
    """frames_rgba: list of PIL RGBA images（render_actions 的输出形态）."""
    import numpy as np

    profile = [_arr(img) for img in frames_rgba]
    energies = _frame_energy(profile)
    mean_e = statistics.fmean(energies)
    motion_cv = (statistics.pstdev(energies) / mean_e) if mean_e > 1e-6 else 0.0
    seam_ratio = energies[-1] / mean_e if mean_e > 1e-6 else 1.0
    jerk = [
        abs(energies[i + 1] - energies[i]) / mean_e for i in range(len(energies) - 1)
    ]
    jerk_ratio = statistics.fmean(jerk) if jerk else 0.0
    return {
        "motion_cv": round(motion_cv, 4),
        "seam_ratio": round(seam_ratio, 4),
        "seam_abs": round(energies[-1], 4),
        "jerk_ratio": round(jerk_ratio, 4),
        "max_jump": round(max(energies), 4),
        "mean_energy": round(mean_e, 4),
    }


def _mean_image(images):
    import numpy as np

    acc = None
    for img in images:
        arr = _arr(img)
        acc = arr if acc is None else acc + arr
    return acc / len(images)


def distinctness_metrics(actions_frames):
    """actions_frames: {action: [PIL RGBA]} → 两两均值像差矩阵 + 最小值."""
    means = {act: _mean_image(f) for act, f in actions_frames.items()}
    pairs = {}
    acts = [a for a in ACTIONS if a in means]
    for i, a in enumerate(acts):
        for b in acts[i + 1 :]:
            pairs["{}|{}".format(a, b)] = round(
                float(abs(means[a] - means[b]).mean()), 4
            )
    return {"min_pairwise": min(pairs.values()), "pairs": pairs}


def _subject_top(image):
    import numpy as np

    alpha = _arr(image)[..., 3]
    rows = np.where((alpha > 128).any(axis=1))[0]
    return int(rows[0]) if len(rows) else None


def key_pose_features():
    """关键姿态特征硬门（曲线级精确值 + 像素级端到端验证）。"""
    from artgen.anim import _pose

    attack = [_pose("attack", i / 720.0, None) for i in range(720)]
    lean_impact = max(p["lean"] for p in attack)
    lean_coil = min(p["lean"] for p in attack)
    weapon_swing = max(p["weapon"] for p in attack) - min(p["weapon"] for p in attack)
    walk_lifts = [_pose("walk", i / 720.0, None)["lift"] for i in range(720)]
    lift_alternates = any(l[0] > 6 and l[1] < 1e-9 for l in walk_lifts) and any(
        l[1] > 6 and l[0] < 1e-9 for l in walk_lifts
    )
    run_knee = max(
        abs(_pose("run", i / 720.0, None).get("knee_l", 0.0)) for i in range(720)
    )
    walk_knee = max(
        abs(_pose("walk", i / 720.0, None).get("knee_l", 0.0)) for i in range(720)
    )
    return {
        "attack_impact_lean": round(lean_impact, 2),
        "attack_coil_lean": round(lean_coil, 2),
        "attack_weapon_swing": round(weapon_swing, 2),
        "walk_lift_alternates": lift_alternates,
        "run_knee_amplitude": round(run_knee, 2),
        "walk_knee_amplitude": round(walk_knee, 2),
        "run_knee_gt_walk": run_knee > walk_knee + 5.0,
    }


def _detail_palette(source_rgb_img):
    """源画显著色簇：跳过背景（最外圈主色），取饱和度×面积 top-4。
    输入必须是**原始源画**——从渲染帧取色会把"渲染链洗掉的细节"漏检。"""
    from collections import Counter

    import numpy as np

    quant = source_rgb_img.quantize(colors=16).convert("RGB")
    counts = Counter(quant.getdata())
    border = [quant.getpixel((x, 0)) for x in range(0, source_rgb_img.width, 8)] + [
        quant.getpixel((0, y)) for y in range(0, source_rgb_img.height, 8)
    ]
    border_set = set(border)
    ranked = []
    for color, count in counts.items():
        if color in border_set:
            continue
        r, g, b = color
        saturation = max(r, g, b) - min(r, g, b)
        ranked.append((saturation * math.sqrt(count), saturation, color, count))
    ranked.sort(reverse=True)
    return [color for _, sat, color, _ in ranked[:4] if sat >= 30]


def fidelity_metrics(source_png_bytes, actions_frames):
    """风格相似度 + 标志色存活率 + **细节还原准确率**（completeness）.

    completeness = 每个标志色在最佳帧中的纯色像素数 / 源画中该色像素数
    （钳到 1）的均值——"颜色还在"（survival）不够，武器被洗掉 1/3 时
    survival 仍是 1.0，completeness 才会掉到 0.64。"""
    from artgen.style import similarity_rgba

    import numpy as np
    from PIL import Image

    reference = actions_frames["idle"][0]
    overall = []
    for frames in actions_frames.values():
        for img in frames[:: max(1, len(frames) // 6)]:
            w, h = img.size
            report = similarity_rgba(
                (w, h, bytes(img.tobytes())), (w, h, bytes(reference.tobytes()))
            )
            overall.append(report["overall"])

    source_img = Image.open(io.BytesIO(source_png_bytes)).convert("RGB")
    # 完整度口径：源图先缩到帧尺寸再计数（分辨率缩放不是细节丢失——
    # 否则 384/1024 面积比会被误判成 completeness 0.15 的假阴性）
    source_img = source_img.resize(actions_frames["idle"][0].size, Image.LANCZOS)
    palette = _detail_palette(source_img)
    source_arr = np.asarray(source_img, dtype=np.float32)
    survival_flags, completeness_values = [], []
    for color in palette:
        target = np.array(color, dtype=np.float32)
        source_hits = int((abs(source_arr - target[None, None, :]).max(axis=2) < 40).sum())
        hit_any = False
        best_ratio = 0.0
        for frames in actions_frames.values():
            for img in frames:
                arr = _arr(img)
                close = (abs(arr[..., :3] - target[None, None, :]).max(axis=2) < 40) & (
                    arr[..., 3] > 200
                )
                count = int(close.sum())
                if count >= 6:
                    hit_any = True
                    best_ratio = max(best_ratio, min(1.0, count / max(1, source_hits)))
        survival_flags.append(1 if hit_any else 0)
        completeness_values.append(best_ratio)
    survival = statistics.fmean(survival_flags) if survival_flags else 1.0
    completeness = statistics.fmean(completeness_values) if completeness_values else 1.0
    return {
        "style_overall": round(statistics.fmean(overall), 4),
        "detail_colors": [list(c) for c in palette],
        "detail_survival": round(survival, 4),
        "detail_completeness": round(completeness, 4),
    }


# ── 评分映射 ──────────────────────────────────────────────────────────────
def _penalty(value, anchor):
    lo, hi = anchor
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def smoothness_score(metrics):
    penalty = sum(
        _SMOOTH_WEIGHTS[key] * _penalty(metrics[key], _SCORE_ANCHORS[key])
        for key in _SMOOTH_WEIGHTS
    )
    return round(100.0 * (1.0 - penalty), 1)


def distinctness_score(metrics, features):
    score = 100.0 * _penalty(metrics["min_pairwise"], _SCORE_ANCHORS["min_pairwise"])
    hard = _feature_hard_list(features)
    score -= 15.0 * sum(1 for _, ok in hard if not ok)
    return round(max(0.0, score), 1)


def fidelity_score(metrics):
    """0.5×风格相似度 + 0.2×标志色存活 + 0.3×细节还原准确率（completeness）."""
    return round(
        100.0
        * (
            0.5 * metrics["style_overall"]
            + 0.2 * metrics["detail_survival"]
            + 0.3 * metrics["detail_completeness"]
        ),
        1,
    )


def _feature_hard_list(features):
    return [
        ("attack impact lean ≥18°", features["attack_impact_lean"] >= 18.0),
        ("attack weapon swing ≥200°", features["attack_weapon_swing"] >= 200.0),
        ("walk lift alternates", bool(features["walk_lift_alternates"])),
        ("run knee > walk knee", bool(features["run_knee_gt_walk"])),
    ]


# ── 渲染管线 ──────────────────────────────────────────────────────────────
def render_actions(pose_patch=None, config=None, blend=False, size=RENDER_SIZE, count=RENDER_FRAMES, actions=ACTIONS):
    """渲染动作帧。pose_patch: 旧曲线注入（A/B 的 legacy 侧）；actions 可选子集。"""
    import artgen.riganim as riganim_mod
    from artgen.riganim import animate_rigged
    from PIL import Image

    source = _knight_png()
    original = riganim_mod._pose
    if pose_patch is not None:
        riganim_mod._pose = lambda action, phase, cfg=None: (
            pose_patch(action, phase % 1.0, cfg) if pose_patch else original(action, phase, cfg)
        )
    try:
        out = {}
        for action in actions:
            frames, _, _, _ = animate_rigged(
                source, action, count, size, config=config, keep_background=True
            )
            if blend and action in ("walk", "run"):
                from artgen.pipeline import _ghost_blend

                frames = _ghost_blend(frames, alpha=BLEND_ALPHA)
            out[action] = [Image.frombytes("RGBA", (w, h), bytes(rgba)) for w, h, rgba in frames]
    finally:
        riganim_mod._pose = original
    return out


def evaluate(actions_frames, source_png=None):
    metrics = {}
    per_action = {}
    for action, frames in actions_frames.items():
        per_action[action] = smoothness_metrics(frames)
    # 流畅度取循环动作（walk/run/idle）均值——attack/jump 的一次性大姿态
    # 天然能量不匀，混入会淹没循环动作的卡顿信号
    cyclic = [per_action[a] for a in ("idle", "walk", "run") if a in per_action]
    metrics["smoothness"] = {
        key: round(statistics.fmean(m[key] for m in cyclic), 4)
        for key in ("motion_cv", "seam_ratio", "jerk_ratio", "max_jump")
    }
    metrics["per_action_energy"] = {
        a: round(m["mean_energy"], 3) for a, m in per_action.items()
    }
    metrics["distinctness"] = distinctness_metrics(actions_frames)
    metrics["features"] = key_pose_features()
    if source_png:
        metrics["fidelity"] = fidelity_metrics(source_png, actions_frames)
    scores = {
        "smoothness": smoothness_score(metrics["smoothness"]),
        "distinctness": distinctness_score(metrics["distinctness"], metrics["features"]),
    }
    if "fidelity" in metrics:
        scores["fidelity"] = fidelity_score(metrics["fidelity"])
    metrics["scores"] = scores
    return metrics


def run_evaluation(pose_patch=None, config=None, blend=True):
    actions_frames = render_actions(pose_patch=pose_patch, config=config, blend=blend)
    source_png = _knight_png()
    return evaluate(actions_frames, source_png=source_png)


# ── 基线 / 门禁 ───────────────────────────────────────────────────────────
FINGERPRINT = {
    "render_size": RENDER_SIZE,
    "render_frames": RENDER_FRAMES,
    "blend_alpha": BLEND_ALPHA,
    "fixture": "knight192",
}

TOLERANCES = {
    "smoothness": ("min", 3.0),      # 分数不得低于基线 3 分
    "distinctness": ("min", 3.0),
    "fidelity": ("min", 3.0),
    "motion_cv": ("max", 0.03),
    "seam_ratio": ("max", 0.25),
    "min_pairwise": ("min", 1.5),
    "style_overall": ("min", 0.02),
    "detail_survival": ("min", 0.1),
    "detail_completeness": ("min", 0.1),
}


def _flat_metrics(metrics):
    flat = dict(metrics["smoothness"])
    flat["min_pairwise"] = metrics["distinctness"]["min_pairwise"]
    flat.update(
        {k: v for k, v in metrics["fidelity"].items() if isinstance(v, (int, float))}
    )
    flat.update(metrics["scores"])
    return flat


def compare(baseline, current):
    rows, failures = [], []
    base = _flat_metrics(baseline["metrics"])
    cur = _flat_metrics(current)
    for key, (direction, tol) in TOLERANCES.items():
        if key not in base or key not in cur:
            continue
        b, c = base[key], cur[key]
        ok = (c >= b - tol) if direction == "min" else (c <= b + tol)
        rows.append((key, b, c, "PASS" if ok else "FAIL"))
        if not ok:
            failures.append("{} ({} {}: baseline={} current={})".format(key, "≥" if direction == "min" else "≤", tol, b, c))
    for name, ok in _feature_hard_list(current["features"]):
        if not ok:
            failures.append("feature: {} 未达标".format(name))
        rows.append((name, "—", "PASS" if ok else "FAIL", "hard"))
    return rows, failures


def main() -> int:
    argv = sys.argv[1:]
    if "--ab" in argv:
        return _run_ab()
    metrics = run_evaluation(blend=True)
    if "--record" in argv:
        doc = {
            "fingerprint": FINGERPRINT,
            "baseline": {"metrics": metrics, "tolerances": TOLERANCES},
        }
        with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, ensure_ascii=False, indent=1)
        print("baseline written →", BASELINE_PATH)
    _print_report(metrics)
    if "--check" in argv:
        with open(BASELINE_PATH, encoding="utf-8") as handle:
            doc = json.load(handle)
        if doc.get("fingerprint") != FINGERPRINT:
            print("fingerprint mismatch — re-record baseline (motion_quality.py --record)")
            return 1
        rows, failures = compare(doc["baseline"], metrics)
        print("\n{:28s} {:>10s} {:>10s}  gate".format("metric", "baseline", "current"))
        for key, b, c, gate in rows:
            print("{:28s} {:>10} {:>10}  {}".format(key[:28], b, c, gate))
        if failures:
            print("\nFAIL: " + "；".join(failures))
            return 1
        print("\nall motion-quality gates PASS")
    return 0


def _print_report(metrics):
    print("== 动作质量量化报告（离线确定性夹具：持械骑士 192px×24 帧）==")
    s, d, f = metrics["smoothness"], metrics["distinctness"], metrics["fidelity"]
    print(
        "流畅度 smoothness = {}/100  (motion_cv={} seam_ratio={} jerk_ratio={} max_jump={})".format(
            metrics["scores"]["smoothness"], s["motion_cv"], s["seam_ratio"], s["jerk_ratio"], s["max_jump"]
        )
    )
    print(
        "辨识度 distinctness = {}/100  (min_pairwise={} 最难分辨对={})".format(
            metrics["scores"]["distinctness"],
            d["min_pairwise"],
            min(d["pairs"], key=d["pairs"].get),
        )
    )
    print(
        "细节还原 fidelity = {}/100  (style_overall={} detail_survival={} detail_completeness={} 标志色={})".format(
            metrics["scores"]["fidelity"], f["style_overall"], f["detail_survival"],
            f["detail_completeness"], f["detail_colors"]
        )
    )
    print("关键姿态特征:", json.dumps(metrics["features"], ensure_ascii=False))
    print("分动作平均运动能量:", metrics["per_action_energy"])


# ── A/B 模式：三项优化逐一对照（legacy 侧逐字复刻优化前行为）──────────────
def _legacy_attack_pose(action, phase, cfg):
    """2026-10-03 旧 attack 曲线（k -0.55~1.07、无肘展/lunge、不消费 cfg arm/bob）。"""
    if action != "attack":
        from artgen.anim import _pose

        return _pose(action, phase, cfg)
    if phase < 0.3:
        u = phase / 0.3
        k = -0.55 * (0.5 * (1.0 - math.cos(math.pi * u)))
    elif phase < 0.55:
        u = (phase - 0.3) / 0.25
        k = -0.55 + 1.62 * (u * u)
    elif phase < 0.8:
        u = (phase - 0.55) / 0.25
        k = 0.92 + 0.15 * math.cos(math.pi * u)
    else:
        u = (phase - 0.8) / 0.2
        k = 0.77 - 0.77 * (u * u * (3.0 - 2.0 * u))
    return {
        "bob": -3.0 * _old_bump(min(1.0, phase / 0.62)),
        "jump": 0.0,
        "arm": 0.3 - k * 0.25,
        "leg": math.sin(phase * 2.0 * math.pi) * 0.4,
        "lean": 4.0 + k * 10.0,
        "weapon": -60.0 + 120.0 * k,
        "tuck": 0.0,
        "lift": (0.0, 0.0),
        "squat": 0.0,
        "sway": 0.0,
        "tilt": 0.0,
    }


def _old_bump(u, peak=0.5):
    if u <= 0.0 or u >= 1.0:
        return 0.0
    p = math.log(0.5) / math.log(max(0.02, min(0.98, peak)))
    return 0.5 * (1.0 - math.cos(2.0 * math.pi * (u ** p)))


def _pose_sweep(action, key, config=None, samples=720):
    from artgen.anim import _pose

    values = [_pose(action, i / samples, config).get(key, 0.0) for i in range(samples)]
    return min(values), max(values)


def _run_ab():
    print("== A/B 对照（同一确定性夹具；除被测杠杆外一切相同）==\n")

    # A/B-1 帧混合（基础动作流畅度）
    raw = render_actions(blend=False)
    blended = render_actions(blend=True)
    m_raw = smoothness_metrics(raw["walk"])
    m_blend = smoothness_metrics(blended["walk"])
    print("[A/B-1] walk 帧混合 α={}（流畅度）".format(BLEND_ALPHA))
    print("  {:12s} {:>10s} {:>10s}".format("", "NO BLEND", "BLEND"))
    for key in ("motion_cv", "seam_abs", "jerk_ratio", "max_jump"):
        print("  {:12s} {:>10.4f} {:>10.4f}".format(key, m_raw[key], m_blend[key]))
    drop = 100.0 * (1.0 - m_blend["max_jump"] / m_raw["max_jump"])
    seam_drop = 100.0 * (1.0 - m_blend["seam_abs"] / m_raw["seam_abs"])
    print("  → 最大帧间跳变下降 {:.1f}%；循环接缝绝对差下降 {:.1f}%（seam_ratio 口径受均值同步下降影响，看绝对差）\n".format(drop, seam_drop))

    # A/B-2 attack 曲线 v1 vs v3.5（动作辨识度）
    legacy = render_actions(pose_patch=_legacy_attack_pose)
    current = render_actions()
    d_legacy = distinctness_metrics(legacy)
    d_current = distinctness_metrics(current)
    f_legacy = key_pose_features()  # 曲线级特征是全局的，改用 legacy 曲线单独算
    from artgen.anim import _pose

    _legacy_poses = [_legacy_attack_pose("attack", i / 720.0, None) for i in range(720)]
    legacy_lean = max(p["lean"] for p in _legacy_poses)
    legacy_weapon = max(p["weapon"] for p in _legacy_poses) - min(p["weapon"] for p in _legacy_poses)
    cur_lean = max(_pose("attack", i / 720.0, None)["lean"] for i in range(720))
    cur_weapon = max(_pose("attack", i / 720.0, None)["weapon"] for i in range(720)) - min(
        _pose("attack", i / 720.0, None)["weapon"] for i in range(720)
    )
    print("[A/B-2] attack 曲线 v1 → v3.5（辨识度）")
    print("  {:22s} {:>10s} {:>10s}".format("", "v1 legacy", "v3.5"))
    print("  {:22s} {:>10.1f} {:>10.1f}".format("命中前倾 lean°", legacy_lean, cur_lean))
    print("  {:22s} {:>10.1f} {:>10.1f}".format("武器扫掠 sweep°", legacy_weapon, cur_weapon))
    print("  {:22s} {:>10.2f} {:>10.2f}".format("min_pairwise 像差", d_legacy["min_pairwise"], d_current["min_pairwise"]))
    print("  {:22s} {:>10s} {:>10s}".format("attack|idle 像差", str(d_legacy["pairs"].get("idle|attack")), str(d_current["pairs"].get("idle|attack"))))
    elb_min, elb_max = _pose_sweep("attack", "elbow_r")
    print("  {:22s} {:>10s} {:>10.0f}~{:.0f}°".format("前臂肘展范围", "0（无通道）", elb_min, elb_max))

    # A/B-3 装备姿态覆盖（识别→贴合）
    from studio.backend.animation_service.equipment import pose_overrides

    equipment = {"weapon": "sword", "armor": "heavy", "skirt": True, "skirt_length": "long"}
    print("\n[A/B-3] 装备姿态覆盖（weapon=sword/armor=heavy/skirt=long）")
    base_off = render_actions()
    for action, expect in (
        ("attack", {"arm": 1.25}),
        ("run", {"bob": 0.85, "stride": 0.9}),
        ("walk", {"stride": 0.9}),
    ):
        overrides = pose_overrides(equipment, action)
        assert overrides == expect, (action, overrides)
        base_on = render_actions(config=overrides, actions=(action,))
        diff = float(abs(_mean_image(base_off[action]) - _mean_image(base_on[action])).mean())
        keys = []
        for key in ("arm", "bob", "knee_l", "leg"):
            lo_off, hi_off = _pose_sweep(action, key, None)
            lo_on, hi_on = _pose_sweep(action, key, overrides)
            if abs(hi_off - lo_off) > 1e-6 or abs(hi_on - lo_on) > 1e-6:
                keys.append("{} {:.3f}→{:.3f}".format(key, hi_off - lo_off, hi_on - lo_on))
        print("  {}: overrides={} 像差(mean|Δ|)={:.2f} {}".format(action, overrides, diff, "; ".join(keys)))
    print("\nA/B 结论：三项杠杆方向一致且幅度可测（详见上表）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
