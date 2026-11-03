"""视频生产管线质量基准（离线、确定性、零额度）。

度量对象是本仓库的**转换管线**（i2v mp4 → 抽帧选帧 → 合成循环动画），
不是生成模型本身——DashScope i2v 是黑盒且按次计费。测试视频为确定性
合成：静态开头（模拟 i2v 首帧静止）+ 非匀速位移与起伏的主体（缓入缓出，
真实 i2v 的运动节奏）+ 水平渐变彩色背景（色彩还原参考）+ 高光/暗部
固定区块（动态范围参考）。

指标体系（对应任务的三类质量要求）::

  loop_seconds          循环时长 = 帧数/fps（本次优化核心目标：+50%）
  frames / fps          采样帧数与播放帧率（帧间隔由 GIF 定长延迟保证均匀）
  sharpness             清晰度：逐帧亮度 Laplacian 标准差均值
  temporal_consistency  时序一致性：相邻帧 similarity_rgba overall 均值
  color_fidelity        色彩还原：逐帧 RGB 直方图与源帧余弦相似度均值
  dynamic_range         动态范围：亮度 1%~99% 分位差（含高光/暗部裁剪率）
  motion_cv             动作流畅度：相邻帧运动能量变异系数（越低越匀）
  motion_mean           平均运动能量（过低 = 近静止/丢动作）
  gif_bytes             产物体积（记录项，防失控软告警）

用法::

  python benchmark/video_quality.py            # 测当前代码一轮 → 写基准 JSON
  python benchmark/video_quality.py --check    # 与基准对比；任一质量指标
                                               # 低于容差 → 打印对照表并退出码 1
"""

import json
import math
import os
import statistics
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from PIL import Image, ImageFilter, ImageStat  # noqa: E402

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_baseline.json")

# ── 基准场景参数（改动会使历史基准不可比，需重录基线）──────────────────
SYNTH_FPS = 24
SYNTH_SIDE = 384
SYNTH_STATIC_HEAD = 12  # i2v 开头的静止原图帧数


def write_synth_video(path, total=120):
    """合成一段 i2v 形态的 mp4：静止开头 + 缓入缓出运动主体 + 彩色渐变
    背景 + 高光/暗部区块。确定性：同参数逐字节一致（编码器时间戳除外）。"""

    import imageio.v2 as imageio

    writer = imageio.get_writer(path, fps=SYNTH_FPS)
    lo_x, hi_x = int(SYNTH_SIDE * 0.12), int(SYNTH_SIDE * 0.62)
    for i in range(total):
        frame = _synth_frame(i, total, lo_x, hi_x)
        writer.append_data(frame)
    writer.close()


def _synth_frame(i, total, lo_x, hi_x):
    import numpy as np

    side = SYNTH_SIDE
    t_cols = np.linspace(0.0, 1.0, side)
    base = np.stack(
        [
            30.0 + (235.0 - 30.0) * t_cols,
            60.0 + (170.0 - 60.0) * t_cols,
            140.0 + (90.0 - 140.0) * t_cols,
        ],
        axis=1,
    )
    frame = np.tile(base[None, :, :], (side, 1, 1))
    # 高光 / 暗部固定区块（动态范围参考）
    frame[12:52, side - 60 : side - 20] = (252, 250, 244)
    frame[side - 56 : side - 16, 16:56] = (16, 16, 20)
    # 主体：缓入缓出水平位移 + 正弦起伏（非匀速 → 均匀采样的帧间运动不均）
    if i >= SYNTH_STATIC_HEAD:
        span = total - SYNTH_STATIC_HEAD - 1
        t = (i - SYNTH_STATIC_HEAD) / max(1, span)
        eased = t * t * (3 - 2 * t)
        x0 = int(lo_x + (hi_x - lo_x) * eased)
        y0 = int(side * 0.42 + math.sin(t * 2.0 * math.pi) * side * 0.05)
    else:
        x0, y0 = lo_x, int(side * 0.42)
    box = 84
    y1 = min(side, y0 + box)
    x1 = min(side, x0 + box)
    frame[y0:y1, x0:x1] = (40, 60, 120)
    return frame.astype(np.uint8)


# ── 指标 ─────────────────────────────────────────────────────────────────────


def _lap_sharpness(gray_img):
    filtered = gray_img.filter(
        ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0), scale=1, offset=0)
    )
    return ImageStat.Stat(filtered).stddev[0]


def _luma_stats(gray_img):
    hist = gray_img.histogram()
    total = sum(hist)
    lo_cut, hi_cut = total * 0.01, total * 0.99
    acc, lo_v, hi_v = 0, 0, 255
    for v, n in enumerate(hist):
        acc += n
        if acc >= lo_cut:
            lo_v = v
            break
    acc = 0
    for v, n in enumerate(hist):
        acc += n
        if acc >= hi_cut:
            hi_v = v
            break
    clip_hi = sum(hist[250:]) / total
    clip_lo = sum(hist[:6]) / total
    return hi_v - lo_v, clip_hi, clip_lo


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def measure(frames_rgba, source_rgb, fps):
    """frames_rgba: [(w,h,rgba)]；source_rgb: 源帧 PIL RGB 图（色彩基准）。"""

    from artgen.style import similarity_rgba

    images = [Image.frombytes("RGBA", (w, h), bytes(rgba)) for w, h, rgba in frames_rgba]
    sharpness = [
        _lap_sharpness(img.convert("L")) for img in images
    ]
    src_hist = source_rgb.histogram()
    color = [
        _cosine(img.convert("RGB").histogram(), src_hist) for img in images
    ]
    spreads, clip_his, clip_los = zip(*[_luma_stats(img.convert("L")) for img in images])
    consistency = [
        similarity_rgba(frames_rgba[i - 1], frames_rgba[i])["overall"]
        for i in range(1, len(frames_rgba))
    ]
    # 运动能量：48×48 灰度帧间差（与 _slice_video 内部同口径）
    energies = []
    for a, b in zip(images[:-1], images[1:]):
        ga = list(a.convert("L").resize((48, 48)).getdata())
        gb = list(b.convert("L").resize((48, 48)).getdata())
        energies.append(sum(abs(x - y) for x, y in zip(ga, gb)) / len(ga))
    mean_energy = statistics.fmean(energies) if energies else 0.0
    cv = (statistics.pstdev(energies) / mean_energy) if energies and mean_energy > 1e-6 else 0.0
    return {
        "frames": len(frames_rgba),
        "fps": fps,
        "loop_seconds": round(len(frames_rgba) / fps, 3),
        "sharpness": round(statistics.fmean(sharpness), 3),
        "temporal_consistency": round(statistics.fmean(consistency), 4) if consistency else 1.0,
        "color_fidelity": round(statistics.fmean(color), 4),
        "dynamic_range_spread": round(statistics.fmean(spreads), 2),
        "clip_high": round(statistics.fmean(clip_his), 5),
        "clip_low": round(statistics.fmean(clip_los), 5),
        # 循环动作总量：采样密度变化下的不变量（每帧能量必然 ∝ 1/帧数，
        # 质量门应盯"动作总量不丢"，而不是单帧能量）
        "motion_total": round(sum(energies), 2),
        "motion_mean": round(mean_energy, 3),
        "motion_cv": round(cv, 4),
    }


# ── 管线执行与基准/对比 ───────────────────────────────────────────────────────


def run_pipeline(min_count, duration, fps=12, size=384):
    """合成视频 → AnimationService._slice_video → compose_animation → 指标。
    顺带冒烟 mp4 直通交付（_deliver_video_mp4）并把交付规格纳入报告。"""

    import tempfile

    import imageio.v2 as imageio

    from artgen import compose_animation

    from studio.backend.animation_service.service import AnimationService

    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = os.path.join(tmp_dir, "synth.mp4")
        write_synth_video(video_path)
        with open(video_path, "rb") as handle:
            video_bytes = handle.read()
        service = AnimationService(tmp_dir)
        # 源帧（色彩基准）= 视频第 0 帧（i2v 形态里的"静态原图"）
        reader = imageio.get_reader(video_path)
        source_rgb = Image.fromarray(next(iter(reader))).convert("RGB")
        reader.close()
        started = time.time()
        frames, info = service._slice_video(
            video_bytes,
            b"",
            fps=fps,
            duration=duration,
            size=size,
            min_count=min_count,
            with_info=True,
        )
        elapsed = time.time() - started
        result = compose_animation(frames_rgba=frames, fps=fps, size=size)
        metrics = measure(frames, source_rgb, fps)
        metrics["pipeline_seconds"] = round(elapsed, 3)
        metrics["gif_bytes"] = len(result["gif"])
        # 交付规格本身是被测对象：GIF 画布尺寸 + 抽帧读到的源帧率
        metrics["delivery_size"] = frames[0][0] if frames else 0
        metrics["source_fps"] = round(float(info.get("source_fps") or 0.0), 3)
        # mp4 直通冒烟：同窗裁剪必须保住源分辨率/帧率（降级则缺省 0，
        # 由容差 ratio_min 拦截）
        spec = service._deliver_video_mp4(video_bytes, info, "benchcheck")
        if spec:
            metrics["mp4_width"] = spec.get("width", 0)
            metrics["mp4_fps"] = spec.get("fps", 0.0)
            metrics["mp4_duration"] = spec.get("duration", 0.0)
            # 码率受编码器版本影响大：只记录不设门
            metrics["mp4_bitrate_kbps"] = spec.get("bitrate_kbps", 0)
        else:
            metrics["mp4_width"] = 0
            metrics["mp4_fps"] = 0.0
            metrics["mp4_duration"] = 0.0
    return metrics


# 质量不降级容差（--check 的硬门；loop 只报告达成率，不设上限）
TOLERANCES = {
    "sharpness": ("ratio_min", 0.97),
    "temporal_consistency": ("abs_min", 0.02),
    "color_fidelity": ("abs_min", 0.01),
    "dynamic_range_spread": ("abs_min", 3.0),
    "motion_total": ("ratio_min", 0.90),
    "motion_cv": ("ratio_max", 1.05),
    # 交付规格门：GIF 画布被静默缩小、抽帧元数据丢帧率、mp4 直通丢
    # 分辨率/帧率/窗口时长，任一发生都算回归
    "delivery_size": ("ratio_min", 0.95),
    "source_fps": ("ratio_min", 0.90),
    "mp4_width": ("ratio_min", 0.90),
    "mp4_fps": ("ratio_min", 0.90),
    "mp4_duration": ("ratio_min", 0.80),
}
GOAL_LOOP_RATIO = 1.5  # 目标：循环时长 +50%（1.67s → 2.5s）


def compare(baseline, current):
    rows, failures = [], []
    base_metrics = dict(baseline["metrics"])
    # R1 基线早于 motion_total 指标：由 frames×motion_mean 合成，保证可对比
    if "motion_total" not in base_metrics and "motion_mean" in base_metrics:
        base_metrics["motion_total"] = round(
            base_metrics["frames"] * base_metrics["motion_mean"], 2
        )
    for key, base_value in base_metrics.items():
        cur = current["metrics"].get(key)
        if cur is None:
            continue
        rule = TOLERANCES.get(key)
        note = ""
        ok = True
        if rule:
            kind, margin = rule
            if kind == "ratio_min":
                ok = cur >= base_value * margin
                note = f"≥ {base_value * margin:.4f}"
            elif kind == "abs_min":
                ok = cur >= base_value - margin
                note = f"≥ {base_value - margin:.4f}"
            elif kind == "ratio_max":
                ok = cur <= base_value * margin
                note = f"≤ {base_value * margin:.4f}"
            if not ok:
                failures.append(key)
        ratio = (cur / base_value) if isinstance(base_value, (int, float)) and base_value else None
        rows.append((key, base_value, cur, ratio, ok, note))
    loop_ratio = current["metrics"]["loop_seconds"] / baseline["metrics"]["loop_seconds"]
    return rows, failures, loop_ratio


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="与已录基线对比")
    parser.add_argument("--min-count", type=int, default=None, help="覆盖采样下限（默认读代码当前值）")
    args = parser.parse_args()

    if args.min_count is not None:
        min_count, duration = args.min_count, 1.0
    else:
        # 与生产路径保持一致：读 AnimationService 调用点的当前默认
        from studio.backend.animation_service.service import (
            VIDEO_SAMPLE_DURATION,
            VIDEO_SAMPLE_MIN_COUNT,
        )

        min_count = VIDEO_SAMPLE_MIN_COUNT
        duration = VIDEO_SAMPLE_DURATION

    current = {
        "config": {"min_count": min_count, "duration": duration, "fps": 12, "size": 384},
        "metrics": run_pipeline(min_count, duration),
        "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print("config:", current["config"])
    for key, value in current["metrics"].items():
        print(f"  {key:24s} {value}")

    if not args.check:
        with open(BASELINE_PATH, "w", encoding="utf-8") as handle:
            json.dump(
                {"baseline": current, "goal_loop_ratio": GOAL_LOOP_RATIO, "tolerances": TOLERANCES},
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print(f"baseline written → {BASELINE_PATH}")
        return 0

    with open(BASELINE_PATH, "r", encoding="utf-8") as handle:
        baseline_doc = json.load(handle)
    baseline = baseline_doc["baseline"]
    rows, failures, loop_ratio = compare(baseline, current)
    print(f"\n{'metric':24s} {'baseline':>10s} {'current':>10s} {'ratio':>7s}  gate")
    for key, base_v, cur, ratio, ok, note in rows:
        mark = "PASS" if ok else "FAIL"
        ratio_text = f"{ratio:.3f}" if ratio is not None else "—"
        print(f"{key:24s} {base_v!s:>10s} {cur!s:>10s} {ratio_text:>7s}  {mark} {note}")
    print(
        f"\nloop ratio vs baseline: ×{loop_ratio:.3f}"
        f"（目标 ≥ ×{GOAL_LOOP_RATIO} → "
        f"{'达成' if loop_ratio >= GOAL_LOOP_RATIO - 0.01 else '未达成'}）"
    )
    if failures:
        print("QUALITY REGRESSION:", "、".join(failures))
        return 1
    print("quality gates: all PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
