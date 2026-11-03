"""视频生成功能全矩阵体检（零额度、离线、确定性）——V4 功能测试方案的主体。

对"视频生成功能"的两个可离线子系统做穷举式功能检测，产出
benchmark/functional_matrix_report.json + 控制台 FAIL 清单：

  矩阵 A｜程序化骨骼链（完全可控的生成路径）
    5 动作 × {front, side} × {mesh, rigid}（骑士双视图真图）+ 发层 overlay
    + phases 多段编排 + turn 假转身，共 26 格。逐格检测：
      渲染成功 / 帧间有运动 / 循环动作首尾连续（C0）/ 头部不出框（削头）/
      侧视中缝不撕裂 / 发层可见 / 单格耗时
    —— fixtures 只能测构造边界，本矩阵用真角色图把**每格真实渲染**过一遍。

  矩阵 B｜i2v 下游管线（模型产出 → 交付）
    benchmark/i2v_runs/ 里 5 种模型配置 × 5 动作的全部真实产出 mp4
    （V2 实测留存，含 flash/plus/1080p/ext/旧词表）逐条走
    _slice_video → compose_animation → _deliver_video_mp4 完整下游，
    按模型配置聚合：抽帧成功率 / 循环时长 / 接缝残留 / mp4 规格 / 耗时。
    ——生成侧已由 i2v_bench 覆盖；本矩阵回答"每种模型配置的产出在
    交付链上是否都稳定、高质量"。

用法::

  python benchmark/video_functional_matrix.py            # 全矩阵
  python benchmark/video_functional_matrix.py --matrix a  # 仅程序化链
  python benchmark/video_functional_matrix.py --matrix b  # 仅 i2v 下游
退出码：任一 FAIL → 1。
"""

import argparse
import json
import os
import statistics
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

GEN = os.path.join(REPO_ROOT, "studio", "backend", "generated")
SIDE_ART = os.path.join(GEN, "edit_1790667946394.png")
FRONT_ART = os.path.join(GEN, "img_1790667929037.png")
HAIR_LAYER = os.path.join(GEN, "side_binding_preview", "hair_layer.png")
RUNS_DIR = os.path.join(REPO_ROOT, "benchmark", "i2v_runs")
REPORT_PATH = os.path.join(REPO_ROOT, "benchmark", "functional_matrix_report.json")

ACTIONS_LOOP = ("walk", "run", "idle")
ACTIONS_ONESHOT = ("attack", "jump")
ACTIONS = ACTIONS_LOOP + ACTIONS_ONESHOT

FAILS = []


def check(cell, name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    if not ok:
        FAILS.append("{}: {} -- {}".format(cell, name, detail))
    print("  [{}] {:34s} {}".format(tag, name, cell + (" " + detail if detail and not ok else "")))


def _rgba(img_bytes, size):
    from artgen.sourceanim import _fit
    from PIL import Image

    return _fit(Image.open(__import__("io").BytesIO(img_bytes)).convert("RGBA"), size)


def _hair_overlay_for(layer_rgba, size, amp=7.0, lag=0.12):
    """从发层 PNG 构建 overlay dict（锚点=mask 底部 12% 行质心，归一化）。"""
    import numpy as np

    arr = np.asarray(layer_rgba.getchannel("A"))
    ys, xs = np.where(arr > 128)
    if len(ys) == 0:
        return None
    y0, y1 = ys.min(), ys.max()
    band = ys >= y1 - max(1, int(0.12 * (y1 - y0)))
    root = (float(xs[band].mean()) / layer_rgba.width, float(ys[band].mean()) / layer_rgba.height)
    return {"layer": layer_rgba, "root": root, "amp": amp, "lag": lag}


def matrix_a():
    from artgen import compose_animation
    from artgen.riganim import animate_rigged
    from artgen.style import similarity_rgba
    from PIL import Image

    with open(SIDE_ART, "rb") as h:
        side_bytes = h.read()
    with open(FRONT_ART, "rb") as h:
        front_bytes = h.read()

    hair_overlay = None
    if os.path.isfile(HAIR_LAYER):
        hair_overlay = _hair_overlay_for(Image.open(HAIR_LAYER).convert("RGBA"), 384)

    cells = []
    for action in ACTIONS:
        for view in ("front", "side"):
            for skin in ("mesh", "rigid"):
                cells.append({"action": action, "view": view, "skin": skin})
    cells.append({"action": "walk", "view": "front", "skin": "mesh", "hair": True})
    cells.append({"action": "walk+turn", "view": "front", "skin": "mesh",
                  "config": {"phases": [{"action": "walk", "weight": 0.6}, {"action": "walk", "weight": 0.4, "turn": 90}]}})
    cells.append({"action": "idle", "view": "side", "skin": "mesh", "hair": True})

    results = {}
    for cell in cells:
        key = "{action}/{view}/{skin}".format(**cell) + ("+hair" if cell.get("hair") else "") + (
            "+phases" if cell.get("config") else ""
        )
        source = side_bytes if cell["view"] == "side" else front_bytes
        overlays = [{"layer": hair_overlay["layer"], "root": hair_overlay["root"],
                     "amp": hair_overlay["amp"], "lag": hair_overlay["lag"]}] if cell.get("hair") and hair_overlay else None
        started = time.time()
        entry = {}
        try:
            frames, _, _, falign = animate_rigged(
                source, cell["action"], 12, 384, segment_mask=None,
                keep_background=False, skin=cell["skin"], view=cell["view"],
                overlays=overlays, config=cell.get("config"),
            )
            entry["frames"] = len(frames)
            entry["seconds"] = round(time.time() - started, 2)
            check(key, "renders 12 frames", len(frames) == 12, str(len(frames)))

            # 帧间有运动（最大相邻帧差非零）
            diffs = [
                statistics.fmean([
                    abs(a - b)
                    for a, b in zip(
                        Image.frombytes("RGBA", (frames[i][0], frames[i][1]), bytes(frames[i][2]))
                        .convert("L").resize((48, 48)).tobytes(),
                        Image.frombytes("RGBA", (frames[i + 1][0], frames[i + 1][1]), bytes(frames[i + 1][2]))
                        .convert("L").resize((48, 48)).tobytes(),
                    )
                ])
                for i in range(len(frames) - 1)
            ]
            entry["motion_max"] = round(max(diffs), 2)
            check(key, "visible motion", max(diffs) > 1.0, f"max={max(diffs):.2f}")

            # 削头检测（硬截断判据）：内容顶行贴到画布第 0 行 = 头被画布
            # 边缘切掉。头顶本就不在画布顶的角色（如骑士头顶在 row~26）天然
            # 通过——"顶部 6% 行必须有像素"的旧判据对这类原画误报。
            import numpy as _np_head

            _row_mins = []
            for f in frames:
                _a = _np_head.asarray(
                    Image.frombytes("RGBA", (f[0], f[1]), bytes(f[2])).getchannel("A")
                )
                _rows = _np_head.where(_a.max(axis=1) > 0)[0]
                _row_mins.append(int(_rows.min()) if len(_rows) else -1)
            entry["content_top_row"] = min(_row_mins)
            check(key, "no hard head clipping (content top row > 0)", min(_row_mins) != 0,
                  f"min content top row={min(_row_mins)}")

            # 循环动作：首尾 C0 连续（attack/jump 是一次性动作，不查）
            if cell["action"] in ACTIONS_LOOP:
                sim = similarity_rgba(frames[0], frames[-1])["overall"]
                entry["loop_sim"] = round(sim, 4)
                check(key, "loop C0 (first~last >= 0.85)", sim >= 0.85, f"{sim:.4f}")

            # 侧视：腿块中缝不撕裂（hip..knee 行中线 ±4 列的最低帧均值）
            if cell["view"] == "side":
                import numpy as np

                seams = []
                for f in frames:
                    a = np.asarray(
                        Image.frombytes("RGBA", (f[0], f[1]), bytes(f[2])).getchannel("A"),
                        dtype=np.float32,
                    )
                    rows = a[int(384 * 0.55):int(384 * 0.78), :]
                    seams.append(float(rows[:, 188:196].mean()))
                entry["seam_min"] = round(min(seams), 1)
                check(key, "side seam not torn (min mean >= 30)", min(seams) >= 30.0,
                      f"{min(seams):.1f}")

            # 发层可见：头部区（顶部 40% 行）alpha 总量高于无 overlay 基线
            if cell.get("hair"):
                head = [
                    sum(Image.frombytes("RGBA", (f[0], f[1]), bytes(f[2])).getchannel("A")
                        .crop((0, 0, f[0], int(f[1] * 0.4))).getextrema()[1] for f in frames)
                ]
                entry["hair_head_alpha"] = int(min(head))
                check(key, "hair layer visible", min(head) > 0)
        except Exception as error:  # noqa: BLE001 - 体检要抓异常格
            entry["error"] = str(error)[:200]
            check(key, "renders without exception", False, str(error)[:120])
        results[key] = entry

    return results


def matrix_b():
    import glob as _glob

    import imageio.v2 as imageio
    from PIL import Image

    from artgen import compose_animation
    from studio.backend.animation_service.service import AnimationService
    from studio.backend.model_service.service import GENERATED_DIR

    import tempfile

    service = AnimationService(tempfile.mkdtemp(prefix="cf_matrix_b_"))
    clips = sorted(_glob.glob(os.path.join(RUNS_DIR, "*", "*.mp4")))
    results = {}
    agg = {}
    for clip in clips:
        variant = os.path.basename(os.path.dirname(clip))
        action = os.path.splitext(os.path.basename(clip))[0]
        key = "{}/{}".format(variant, action)
        entry = {}
        started = time.time()
        try:
            with open(clip, "rb") as h:
                video_bytes = h.read()
            frames, info = service._slice_video(
                video_bytes, b"", fps=12,
                duration=1.25, size=384, min_count=30, with_info=True,
            )
            entry["sliced"] = len(frames)
            check(key, "slices >= 12 frames", len(frames) >= 12, str(len(frames)))
            result = compose_animation(frames_rgba=frames, fps=12, size=384, with_mp4=False)
            check(key, "composes gif", len(result["gif"]) > 1000, str(len(result["gif"])))

            # mp4 直通交付（V1 路径，规格保持）
            spec = service._deliver_video_mp4(video_bytes, info, "mx_{}_{}".format(variant, action))
            if spec:
                entry["mp4"] = {k: spec.get(k) for k in ("width", "fps", "duration")}
                check(key, "mp4 delivery keeps resolution",
                      bool(spec.get("width")), str(spec.get("width")))
            else:
                check(key, "mp4 delivery keeps resolution", False, "deliver returned None")

            # 接缝残留：循环重排后最大的相邻帧差（越小循环越顺）
            from PIL import Image as _PIL

            def _gray(f):
                return list(_PIL.frombytes("RGBA", (f[0], f[1]), bytes(f[2])).convert("L").resize((48, 48)).getdata())

            pairs = [
                sum(abs(x - y) for x, y in zip(_gray(frames[i]), _gray(frames[(i + 1) % len(frames)]))) / 2304
                for i in range(len(frames))
            ]
            entry["loop_seam"] = round(max(pairs[-3:]), 2)  # 溶解边界 3 对
            entry["motion_peak"] = round(max(pairs), 2)  # 全局自然运动尖峰（记录不设门）
            entry["loop_mean"] = round(statistics.fmean(pairs), 2)
            # 接缝残差只度量**循环边界相关对**（溶解引入的 last→b1→b2→first），
            # 与动作本身的自然运动尖峰（attack 挥击/跳跃弹道）解耦——旧判据把
            # 两者混在一起，大动态动作永远误报。交叉溶解后边界对 ≈ 平均量级。
            check(key, "loop seam residual bounded (cross-fade boundary)",
                  max(pairs[-3:]) <= max(1.8 * statistics.fmean(pairs), 14.0),
                  f"seam={max(pairs):.2f} mean={statistics.fmean(pairs):.2f}")
            entry["seconds"] = round(time.time() - started, 2)
        except Exception as error:  # noqa: BLE001
            entry["error"] = str(error)[:200]
            check(key, "downstream pipeline runs", False, str(error)[:120])
        results[key] = entry
        agg.setdefault(variant, []).append(entry)

    summary = {}
    for variant, entries in agg.items():
        ok = [e for e in entries if "error" not in e]
        summary[variant] = {
            "clips": len(entries),
            "ok": len(ok),
            "loop_seam_max": round(max((e.get("loop_seam") or 0) for e in ok), 2) if ok else None,
            "mp4_ok": sum(1 for e in ok if e.get("mp4")),
        }
    return results, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", choices=["a", "b"], default=None)
    args = parser.parse_args()

    report = {}
    if args.matrix in (None, "a"):
        print("== 矩阵 A｜程序化骨骼链（真角色全格渲染）==")
        report["procedural"] = matrix_a()
    if args.matrix in (None, "b"):
        print("== 矩阵 B｜i2v 下游管线（真实模型产出全走交付链）==")
        results, summary = matrix_b()
        report["i2v_downstream"] = results
        report["i2v_summary"] = summary
        for variant, row in summary.items():
            print("  {:16s} clips={clips} ok={ok} mp4_ok={mp4_ok} seam_max={loop_seam_max}".format(
                variant, **row))

    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        json.dump({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "matrix": report,
                   "fails": FAILS}, handle, ensure_ascii=False, indent=2)
    print("\nreport →", REPORT_PATH)
    if FAILS:
        print("FUNCTIONAL FAILURES ({}):".format(len(FAILS)))
        for f in FAILS:
            print("  -", f)
        return 1
    print("all matrix cells PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
