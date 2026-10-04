"""MOS 盲评包生成与解码（V4 主观评测，零额度）。

把 benchmark/i2v_runs/ 的 A/B 样片随机代号化，生成本地 HTML 评分页——
评分者只看到代号，不知道来源；评分回传后用 --decode 解码出对照表。

用法::

  python benchmark/mos_kit.py                 # 生成/刷新盲评包 → benchmark/mos_kit/
  python benchmark/mos_kit.py --decode 评分.json   # 解码评分 → 打印对照表并落盘
"""

import argparse
import html
import json
import os
import random
import shutil
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT_DIR = os.path.join(REPO_ROOT, "benchmark", "mos_kit")
CLIPS_DIR = os.path.join(KIT_DIR, "clips")
KEY_PATH = os.path.join(KIT_DIR, "key.json")
RUNS_DIR = os.path.join(REPO_ROOT, "benchmark", "i2v_runs")
AB_DIR = os.path.join(REPO_ROOT, "studio", "backend", "generated", "side_binding_preview")
ACTIONS = ["walk", "run", "attack", "jump", "idle"]
VARIANTS = ["flash_v1", "flash_v2", "flash_v2_ext", "plus_v2", "flash_v2_1080p"]
DIMENSIONS = ["清晰度", "流畅度", "一致性", "真实感", "整体"]


def _code(rng, used):
    while True:
        code = "{}{}".format(rng.choice("KMQXZ"), rng.randrange(100, 999))
        if code not in used:
            used.add(code)
            return code


def build():
    rng = random.Random(20261004)  # 确定性：同源样片刷新后代号稳定
    used = set()
    entries = []  # (code, rel_path, group, source)
    os.makedirs(CLIPS_DIR, exist_ok=True)

    for variant in VARIANTS:
        for action in ACTIONS:
            src = os.path.join(RUNS_DIR, variant, "{}.mp4".format(action))
            if not os.path.isfile(src):
                continue
            code = _code(rng, used)
            dst = os.path.join(CLIPS_DIR, code + ".mp4")
            shutil.copyfile(src, dst)
            entries.append({"code": code, "file": "clips/{}.mp4".format(code),
                            "group": "i2v", "source": "{}/{}".format(variant, action)})

    # mesh vs rigid A/B（骑士侧视 walk，GIF）
    for src_name, label in (("ab_walk_mesh.gif", "mesh/rigid-A"), ("ab_walk_rigid.gif", "mesh/rigid-B")):
        src = os.path.join(AB_DIR, src_name)
        if os.path.isfile(src):
            code = _code(rng, used)
            shutil.copyfile(src, os.path.join(CLIPS_DIR, code + ".gif"))
            entries.append({"code": code, "file": "clips/{}.gif".format(code),
                            "group": "skin_ab", "source": label})

    with open(KEY_PATH, "w", encoding="utf-8") as handle:
        json.dump({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "entries": entries},
                  handle, ensure_ascii=False, indent=2)

    _write_rating_html(entries)
    print("kit built: {} clips → {}".format(len(entries), KIT_DIR))
    print("评分页：benchmark/mos_kit/评分.html（浏览器打开，评分完导出 JSON）")
    print("代号对照（评分前勿看）：", KEY_PATH)


def _write_rating_html(entries):
    items = []
    for entry in entries:
        selects = "".join(
            '<label>{d}<select data-code="{c}" data-dim="{d}">'
            '<option value=""></option>{opts}</select></label>'.format(
                d=html.escape(d), c=entry["code"],
                opts="".join('<option value="{}">{}</option>'.format(v, v) for v in range(1, 6)),
            )
            for d in DIMENSIONS
        )
        # GIF 用 <img>（<video> 不播 GIF——首轮盲评 mesh/rigid 两条因此黑屏）
        if entry["file"].endswith(".gif"):
            player = '<img src="{f}" alt="{c}">'.format(f=entry["file"], c=entry["code"])
        else:
            player = '<video src="{f}" loop muted autoplay playsinline controls></video>'.format(
                f=entry["file"]
            )
        items.append(
            '<div class="clip"><h3>{c}</h3>{p}'
            '<div class="dims">{s}</div><input class="note" data-code="{c}" placeholder="备注（可选）"></div>'.format(
                c=entry["code"], p=player, s=selects,
            )
        )
    page = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>MOS 盲评</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:1080px;margin:24px auto;padding:0 16px;background:#f1efe9;color:#222}
 .clip{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px;margin:14px 0}
 .clip video,.clip img{max-width:420px;width:100%;background:#241f1c;border-radius:8px}
 .dims{display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;font-size:13px}
 select{margin-left:4px}
 .note{margin-top:8px;width:96%}
 button{padding:10px 18px;font-size:15px;cursor:pointer}
 textarea{width:100%;height:140px;margin-top:10px;font-family:monospace}
 h1{font-size:20px}.tip{color:#666;font-size:13px}
</style></head><body>
<h1>视频质量盲评（5 维 × 1~5 分）</h1>
<p class="tip">每条看几秒再打分：清晰度（边缘/纹理干净）、流畅度（不卡不跳）、一致性（角色不漂移、循环无缝）、真实感（运动像有重量和物理）、整体印象。1=很差 5=很好，看不出来就留空。全部打完点底部按钮，把 JSON 复制发回即可。</p>
__ITEMS__
<button onclick="export_()">生成评分 JSON</button>
<textarea id="out" readonly></textarea>
<script>
function export_(){
  const out={};
  document.querySelectorAll("[data-code]").forEach(el=>{
    const c=el.dataset.code; out[c]=out[c]||{};
    if(el.dataset.dim) out[c][el.dataset.dim]=el.value?Number(el.value):null;
    else if(el.classList.contains("note")) out[c].notes=el.value||"";
  });
  document.getElementById("out").value=JSON.stringify(out,null=1?null:2?null:1);
}
</script></body></html>"""
    # 导出时数值化：修正上面占位（保持简单：JSON.stringify(out,null,1)）
    page = page.replace('JSON.stringify(out,null=1?null:2?null:1)', "JSON.stringify(out,null,1)")
    page = page.replace("__ITEMS__", "\n".join(items))
    with open(os.path.join(KIT_DIR, "评分.html"), "w", encoding="utf-8") as handle:
        handle.write(page)


def decode(answers_path):
    with open(KEY_PATH, encoding="utf-8") as handle:
        key = {e["code"]: e for e in json.load(handle)["entries"]}
    with open(answers_path, encoding="utf-8") as handle:
        answers = json.load(handle)
    rows = []
    for code, dims in answers.items():
        source = key.get(code, {}).get("source", "?")
        vals = {d: dims.get(d) for d in DIMENSIONS}
        rows.append((source, code, vals, dims.get("notes") or ""))
    rows.sort()
    print("{:28s} {:>6s} {:>8s} {:>8s} {:>8s} {:>8s} {:>8s}".format(
        "source", "code", "清晰度", "流畅度", "一致性", "真实感", "整体"))
    agg = {}
    for source, code, vals, notes in rows:
        print("{:28s} {:>6s} {:>8} {:>8} {:>8} {:>8} {:>8} {}".format(
            source, code, *(vals[d] if vals[d] is not None else "—" for d in DIMENSIONS),
            notes[:20]))
        for d, v in vals.items():
            if v is not None:
                agg.setdefault(d, []).append(v)
    print("\n== 均值 ==")
    for d, vals_ in agg.items():
        print("{:8s} {:.2f} (n={})".format(d, sum(vals_) / len(vals_), len(vals_)))
    out_path = os.path.join(KIT_DIR, "mos_decoded_{}.json".format(time.strftime("%Y%m%d_%H%M%S")))
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({"rows": [
            {"source": s, "code": c, "scores": v, "notes": n} for s, c, v, n in rows
        ], "aggregate": {d: round(sum(v) / len(v), 3) for d, v in agg.items()}},
            handle, ensure_ascii=False, indent=2)
    print("decoded →", out_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decode", type=str, default=None, help="解码评分 JSON")
    args = parser.parse_args()
    if args.decode:
        return decode(args.decode)
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
