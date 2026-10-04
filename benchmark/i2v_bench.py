"""V2 i2v 基准集：模型档位 / 运动词表 / prompt_extend 对比评测。

**真实计费脚本**——每次未命中缓存的运行都产生真实 DashScope 花费
（flash 1.25 元/条、plus 3.50 元/条）。generate_video 自带 mp4 缓存：
同（模型+提示词+源图+负面词）重复运行零计费，重跑本脚本安全。

基准设计（V2）：
  固定角色   studio/backend/generated/img_1790667929037.png（星辉剑士，onetake 同源）
  动作集     walk / run / attack / jump / idle（正面视角，词表视角无关）
  变体       flash_v1      flash + v1 旧词表（基线）
             flash_v2      flash + v2 运动学词表
             flash_v2_ext  flash + v2 + prompt_extend（官方提示词增强）
             plus_v2       plus + v2（定稿档画质）
             flash_v2_1080p flash + v2 + 1920*1080（分辨率上限探测）
  指标       sharpness / temporal_consistency / motion_total / motion_cv /
             color_fidelity(对源图) / 分辨率 / 帧率 / 时长 / 延迟 / 体积

用法::
  python benchmark/i2v_bench.py --probe                 # 仅能力探测（模型存在性）
  python benchmark/i2v_bench.py --variants flash_v2     # 跑指定变体
  python benchmark/i2v_bench.py                          # 全变体
"""

import argparse
import base64
import json
import os
import statistics
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from PIL import Image  # noqa: E402

from studio.backend.animation_service.service import MOTION_PROMPTS  # noqa: E402

ASSET = os.path.join(REPO_ROOT, "studio", "backend", "generated", "img_1790667929037.png")
OUT_DIR = os.path.join(REPO_ROOT, "benchmark", "i2v_runs")
REPORT_PATH = os.path.join(REPO_ROOT, "benchmark", "i2v_report.json")
CAPABILITY_PATH = os.path.join(REPO_ROOT, "benchmark", "dashscope_capability.json")

ACTIONS = ["walk", "run", "attack", "jump", "idle"]

# v1 旧词表（升级前的 MOTION_PROMPTS，作为基线组保留在此）
OLD_PROMPTS = {
    "walk": (
        "The character walks in place, keeping exactly the same facing direction, "
        "viewpoint and pose orientation as the input image: the legs alternate lifting "
        "and stepping naturally, the arms swing gently in counter-phase, the hips and "
        "torso sway subtly with each step, the upper body stays upright and calm, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked, the motion loops seamlessly."
    ),
    "run": (
        "The character runs in place, keeping exactly the same facing direction and "
        "viewpoint as the input image: quick energetic strides, the arms pumping in "
        "counter-phase, hair and clothes bouncing with the motion, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked, the motion loops seamlessly."
    ),
    "attack": (
        "The character performs one single committed attack in place, keeping exactly "
        "the same facing direction and viewpoint as the input image: a brief coil back, "
        "then a decisive strike with the leading arm extending naturally, then settle "
        "back into the original stance, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked."
    ),
    "jump": (
        "The character jumps straight up in place, keeping exactly the same facing "
        "direction and viewpoint as the input image: a small crouch, a vertical hop "
        "with the legs tucking slightly, then landing back into the starting stance, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked."
    ),
    "idle": (
        "The character breathes gently in place, keeping exactly the same facing "
        "direction and viewpoint as the input image: the torso slowly rises and falls, "
        "subtle head and shoulder movement, everything else stays still, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked, the motion loops seamlessly."
    ),
}

# 能力探测：疑似存在的模型名（存在的会被接受并开始计费→顺带出样片，
# 不存在的立即 400 Model not exist 零费用）
PROBE_MODELS = [
    "wan2.5-i2v-flash",
    "wan2.5-i2v-plus",
    "wan2.2-i2v-flf2v",
    "wan2.2-i2v-flash-audio",
    "wanx2.1-i2v-plus",
]


def _variant_settings(variant):
    from studio.backend.model_service.service import ModelSettingsStore

    settings = dict(ModelSettingsStore().effective())
    cfg = VARIANTS[variant]
    settings["video_model"] = cfg["model"]
    settings["video_prompt_extend"] = cfg.get("extend", False)
    settings["video_size"] = cfg.get("size", "1280*720")
    return settings


def measure_mp4(path, source_rgb):
    """对 i2v 原始 mp4 测指标（固定 1/5 采样，确定性）。"""
    import imageio.v2 as imageio
    import numpy as np
    from PIL import Image

    from benchmark.video_quality import _cosine, _lap_sharpness
    from artgen.style import similarity_rgba

    reader = imageio.get_reader(path)
    try:
        meta = reader.get_meta_data()
        fps = float(meta.get("fps") or 0.0)
        total = 0
        frames = []
        for frame in reader:
            if total % 5 == 0:
                frames.append(frame)
            total += 1
    finally:
        reader.close()
    if fps <= 0 or total < 4 or not frames:
        return {"error": "undecodable or too short", "total": total, "fps": fps}

    pil_frames = [Image.fromarray(f).convert("RGBA") for f in frames]
    gray = [f.convert("L") for f in pil_frames]
    sharp = [_lap_sharpness(g) for g in gray]
    consistency = [
        similarity_rgba(
            (pil_frames[i - 1].width, pil_frames[i - 1].height, pil_frames[i - 1].tobytes()),
            (pil_frames[i].width, pil_frames[i].height, pil_frames[i].tobytes()),
        )["overall"]
        for i in range(1, len(pil_frames))
    ]
    src_hist = source_rgb.histogram()
    color = [_cosine(f.convert("RGB").histogram(), src_hist) for f in pil_frames]
    energies = []
    for a, b in zip(gray[:-1], gray[1:]):
        ga = list(a.resize((48, 48)).getdata())
        gb = list(b.resize((48, 48)).getdata())
        energies.append(sum(abs(x - y) for x, y in zip(ga, gb)) / len(ga))
    mean_e = statistics.fmean(energies) if energies else 0.0
    cv = (statistics.pstdev(energies) / mean_e) if energies and mean_e > 1e-6 else 0.0
    w, h = pil_frames[0].size
    return {
        "width": w,
        "height": h,
        "fps": round(fps, 3),
        "total_frames": total,
        "duration": round(total / fps, 3),
        "sharpness": round(statistics.fmean(sharp), 3),
        "temporal_consistency": round(statistics.fmean(consistency), 4) if consistency else 1.0,
        "color_fidelity_vs_input": round(statistics.fmean(color), 4),
        "motion_total": round(sum(energies), 2),
        "motion_mean": round(mean_e, 3),
        "motion_cv": round(cv, 4),
    }


def run_variant(variant, actions):
    from studio.backend.animation_service.service import FRAMING_CLAUSE
    from studio.backend.model_service.service import generate_video

    cfg = VARIANTS[variant]
    prompts = cfg["prompts"]
    settings = _variant_settings(variant)
    with open(ASSET, "rb") as handle:
        image_bytes = handle.read()
    source_rgb = Image.open(__import__("io").BytesIO(image_bytes)).convert("RGB")

    out_dir = os.path.join(OUT_DIR, variant)
    os.makedirs(out_dir, exist_ok=True)
    runs = {}
    for action in actions:
        prompt = prompts[action] + " " + FRAMING_CLAUSE
        out_path = os.path.join(out_dir, "{}.mp4".format(action))
        started = time.time()
        try:
            video_bytes, used_model = generate_video(settings, prompt, image_bytes)
        except Exception as error:  # noqa: BLE001 - 单条失败不拖垮整组
            runs[action] = {"error": str(error)[:200]}
            print("  [{}] {} FAILED: {}".format(variant, action, str(error)[:120]))
            continue
        latency = round(time.time() - started, 1)
        with open(out_path, "wb") as handle:
            handle.write(video_bytes)
        m = measure_mp4(out_path, source_rgb)
        m.update(
            {
                "latency_s": latency,
                "bytes": len(video_bytes),
                "requested_model": cfg["model"],
                "billed_model": used_model,
                "prompt_version": "v1" if prompts is OLD_PROMPTS else "v2",
                "prompt_extend": cfg.get("extend", False),
                "cached": latency < 3.0,  # 秒回 = 缓存命中
            }
        )
        runs[action] = m
        print(
            "  [{}] {} sharp={} tcon={} mcv={} {}x{}@{} {}s {:.1f}s {}".format(
                variant, action, m.get("sharpness"), m.get("temporal_consistency"),
                m.get("motion_cv"), m.get("width"), m.get("height"), m.get("fps"),
                m.get("duration"), latency, "(cache)" if m.get("cached") else "",
            )
        )
    return runs


def aggregate(runs_by_variant):
    keys = ("sharpness", "temporal_consistency", "motion_total", "motion_cv",
            "color_fidelity_vs_input", "duration", "fps", "width", "latency_s")
    table = {}
    for variant, runs in runs_by_variant.items():
        ok = [r for r in runs.values() if "error" not in r]
        table[variant] = {}
        for key in keys:
            vals = [r[key] for r in ok if key in r]
            table[variant][key] = round(statistics.fmean(vals), 4) if vals else None
        table[variant]["runs_ok"] = len(ok)
        table[variant]["runs_total"] = len(runs)
    return table


def probe():
    """模型存在性探测：400=不存在（零费用）；接受=在线（计费+顺带采样）。"""
    import base64 as _b64
    import httpx

    from studio.backend.animation_service.service import FRAMING_CLAUSE
    from studio.backend.model_service.service import (
        DASHSCOPE_HOST,
        ModelSettingsStore,
        poll_video_task,
    )
    from studio.backend.model_service.service import _video_negative_prompt

    settings = ModelSettingsStore().effective()
    key = settings["api_key"]
    with open(ASSET, "rb") as handle:
        encoded = _b64.b64encode(handle.read()).decode()
    prompt = MOTION_PROMPTS["walk"] + " " + FRAMING_CLAUSE
    results = {}
    for model in PROBE_MODELS:
        entry = {}
        try:
            resp = httpx.post(
                DASHSCOPE_HOST + "/api/v1/services/aigc/video-generation/video-synthesis",
                headers={
                    "Authorization": "Bearer " + key,
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json={
                    "model": model,
                    "input": {"prompt": prompt, "img_url": "data:image/png;base64," + encoded},
                    "parameters": {
                        "size": "1280*720",
                        "prompt_extend": False,
                        "watermark": False,
                        "negative_prompt": _video_negative_prompt(settings),
                    },
                },
                timeout=60,
            )
            if resp.status_code >= 400:
                entry = {"online": False, "status": resp.status_code, "error": resp.text[:150]}
            else:
                task_id = (resp.json().get("output") or {}).get("task_id")
                entry = {"online": True, "task_id": task_id}
                print("probe {}: ONLINE, polling sample...".format(model))
                url = poll_video_task(key, task_id, 420.0)
                data = httpx.get(url, timeout=120).content
                sample_path = os.path.join(OUT_DIR, "probe_{}.mp4".format(model))
                os.makedirs(OUT_DIR, exist_ok=True)
                with open(sample_path, "wb") as handle:
                    handle.write(data)
                source_rgb = Image.open(ASSET).convert("RGB")
                entry["sample"] = dict(
                    measure_mp4(sample_path, source_rgb), bytes=len(data)
                )
        except Exception as error:  # noqa: BLE001 - 探测失败记录即 return
            entry["probe_error"] = str(error)[:200]
        results[model] = entry
        print("probe {}: {}".format(model, json.dumps(entry, ensure_ascii=False)[:160]))
    with open(CAPABILITY_PATH, "w", encoding="utf-8") as handle:
        json.dump({"probed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "models": results}, handle,
                  ensure_ascii=False, indent=2)
    print("capability report →", CAPABILITY_PATH)
    return results


VARIANTS = {
    "flash_v1": {"model": "wan2.2-i2v-flash", "extend": False, "prompts": OLD_PROMPTS},
    "flash_v2": {"model": "wan2.2-i2v-flash", "extend": False, "prompts": MOTION_PROMPTS},
    "flash_v2_ext": {"model": "wan2.2-i2v-flash", "extend": True, "prompts": MOTION_PROMPTS},
    "plus_v2": {"model": "wan2.2-i2v-plus", "extend": False, "prompts": MOTION_PROMPTS},
    "flash_v2_1080p": {"model": "wan2.2-i2v-flash", "extend": False, "prompts": MOTION_PROMPTS,
                        "size": "1920*1080"},
    # 探测发现的在线上世代模型（960×960@30fps 样片已测）：作跨世代参照
    "wanx_v2": {"model": "wanx2.1-i2v-plus", "extend": False, "prompts": MOTION_PROMPTS},
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true", help="仅能力探测")
    parser.add_argument("--variants", type=str, default=None, help="逗号分隔变体列表")
    args = parser.parse_args()

    from PIL import Image

    if args.probe:
        probe()
        return 0

    if not os.path.isfile(ASSET):
        print("benchmark asset missing:", ASSET)
        return 1

    from studio.backend.model_service import usage as usage_mod

    ledger_before = usage_mod.usage_summary()["totals"]["month"]

    names = args.variants.split(",") if args.variants else list(VARIANTS)
    price = {"wan2.2-i2v-flash": 1.25, "wan2.2-i2v-plus": 3.5}
    est = sum(price.get(VARIANTS[n]["model"], 1.25) * len(ACTIONS) for n in names)
    print("variants: {} | est. spend if all uncached: ~{:.1f} CNY".format(names, est))

    report = {}
    if os.path.isfile(REPORT_PATH):
        with open(REPORT_PATH, "r", encoding="utf-8") as handle:
            report = json.load(handle).get("runs", {})
    for name in names:
        print("== variant {} ==".format(name))
        report[name] = run_variant(name, ACTIONS)
        with open(REPORT_PATH, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "asset": os.path.basename(ASSET),
                    "runs": report,
                    "aggregate": aggregate(report),
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )

    print("\n== aggregate ==")
    table = aggregate(report)
    header = "{:16s} {:>8s} {:>8s} {:>8s} {:>8s} {:>8s} {:>7s} {:>7s}".format(
        "variant", "sharp", "tcon", "mtotal", "mcv", "color", "w", "lat_s")
    print(header)
    for variant, row in table.items():
        print("{:16s} {:>8} {:>8} {:>8} {:>8} {:>8} {:>7} {:>7}".format(
            variant, row.get("sharpness"), row.get("temporal_consistency"),
            row.get("motion_total"), row.get("motion_cv"),
            row.get("color_fidelity_vs_input"), row.get("width"),
            row.get("latency_s")))

    ledger_after = usage_mod.usage_summary()["totals"]["total"]
    print("session video spend (ledger delta): ~{:.2f} CNY".format(ledger_after - ledger_before))
    print("report →", REPORT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
