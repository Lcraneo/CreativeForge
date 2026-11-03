"""i2v 武器保持子句真实 A/B（花额度：2 条 flash 草稿 ≈2.5 元）.

A = equipment_aware True（识别→装备上下文 + attack 武器保持子句）
B = equipment_aware False（无装备信息）
其余一切相同（同源图/同动作/同模型档/同采样）。同参命中视频缓存，
重跑本脚本零计费。度量：武器（青色剑刃）色存活率 + 细节完整度 +
motion_cv + 循环接缝。

Run: python benchmark/i2v_weapon_ab.py [--source <png>]
"""

import io
import json
import os
import statistics
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i2v_weapon_ab_report.json")
DEFAULT_SOURCE = os.path.join(
    REPO_ROOT, "studio", "backend", "generated", "edit_1791077182024.png"
)  # 白甲持剑骑士（青色发光剑刃）


def _blade_palette(source_bytes):
    """从源画提取剑刃色簇：青色系（G/B 高、R 低）且非背景蓝。"""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(source_bytes)).convert("RGB")
    arr = np.asarray(img, dtype=np.float32)
    # 青色剑刃：R 低、G 高、B 高、|G-B| 中等；背景宝蓝 R~G 低 B 极高
    cyan = (arr[..., 0] < 150) & (arr[..., 1] > 150) & (arr[..., 2] > 140)
    if not cyan.any():
        return None
    ys, xs = np.nonzero(cyan)
    colors = arr[cyan]
    median = np.median(colors, axis=0)
    return {"color": [round(float(v), 1) for v in median], "pixels": int(cyan.sum())}


def _blade_metrics(frames_rgba, blade_color):
    """逐帧青色剑刃像素数 → 存活率（占比≥5% 峰值的帧数比例）+ 完整度。"""
    import numpy as np
    from PIL import Image

    target = np.array(blade_color, dtype=np.float32)
    counts = []
    for w, h, rgba in frames_rgba:
        arr = np.asarray(Image.frombytes("RGBA", (w, h), bytes(rgba)), dtype=np.float32)
        close = (abs(arr[..., :3] - target[None, None, :]).max(axis=2) < 60) & (arr[..., 3] > 200)
        counts.append(int(close.sum()))
    peak = max(counts) or 1
    alive = sum(1 for c in counts if c >= 0.05 * peak)
    return {
        "blade_peak_px": peak,
        "blade_alive_ratio": round(alive / max(1, len(counts)), 4),
        "blade_mean_px": round(statistics.fmean(counts), 1),
    }


def _smoothness(frames_rgba):
    """motion_cv + 首尾接缝（与 motion_quality 同口径，输入为 GIF 帧序列）."""
    import numpy as np
    from PIL import Image

    profile = [
        np.asarray(Image.frombytes("RGBA", (w, h), bytes(rgba)), dtype=np.float32)
        for w, h, rgba in frames_rgba
    ]
    energies = [float(abs(profile[i] - profile[(i + 1) % len(profile)]).mean()) for i in range(len(profile))]
    mean_e = statistics.fmean(energies)
    return {
        "motion_cv": round(statistics.pstdev(energies) / mean_e, 4) if mean_e > 1e-6 else 0.0,
        "seam_abs": round(energies[-1], 4),
        "mean_energy": round(mean_e, 4),
    }


def main() -> int:
    from studio.backend.animation_service.service import AnimationService
    from studio.backend.model_service.service import ModelSettingsStore

    source_path = DEFAULT_SOURCE
    if "--source" in sys.argv:
        source_path = sys.argv[sys.argv.index("--source") + 1]
    with open(source_path, "rb") as handle:
        source = handle.read()

    settings = ModelSettingsStore().effective()
    if not (settings.get("enabled") and settings.get("api_key")):
        print("model settings not configured — nothing to A/B")
        return 1
    blade = _blade_palette(source)
    print("blade palette:", blade)

    service = AnimationService(os.path.join(REPO_ROOT, "studio", "backend", "generated"))
    results = {}
    for arm, aware in (("A_equipment_on", True), ("B_equipment_off", False)):
        print("generating arm", arm, "... (60~120s)")
        meta = service.create_video(
            source_bytes=source,
            settings=settings,
            action="attack",
            fps=12,
            duration=1.25,
            size=384,
            equipment_aware=aware,
        )
        frames = []
        for index in range(meta["frames"]):
            path = service.path("{}_f{:02d}.png".format(meta["id"], index))
            with open(path, "rb") as handle:
                from artgen.gif import decode_image

                frames.append(decode_image(handle.read()))
        entry = {
            "animation_id": meta["id"],
            "video_model": meta.get("video_model"),
            "quality_tier": meta.get("quality_tier"),
            "equipment": meta.get("equipment"),
            "equipment_prompt_clauses": meta.get("equipment_prompt_clauses", False),
            "prompt": (meta.get("motion_prompt") or "")[:400],
            "blade": _blade_metrics(frames, blade["color"]) if blade else None,
            "smoothness": _smoothness(frames),
        }
        results[arm] = entry
        print(json.dumps(entry, ensure_ascii=False, indent=1)[:800])

    a, b = results["A_equipment_on"], results["B_equipment_off"]
    print("\n== i2v 武器保持子句 A/B ==")
    print("A(子句开) blade_alive_ratio={} blade_mean_px={} | B(关) alive={} mean_px={}".format(
        a["blade"]["blade_alive_ratio"], a["blade"]["blade_mean_px"],
        b["blade"]["blade_alive_ratio"], b["blade"]["blade_mean_px"]))
    print("A motion_cv={} seam_abs={} | B motion_cv={} seam_abs={}".format(
        a["smoothness"]["motion_cv"], a["smoothness"]["seam_abs"],
        b["smoothness"]["motion_cv"], b["smoothness"]["seam_abs"]))
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        json.dump({"source": source_path, "arms": results}, handle, ensure_ascii=False, indent=1)
    print("report →", REPORT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
