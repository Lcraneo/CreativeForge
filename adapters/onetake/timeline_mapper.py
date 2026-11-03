"""timeline_mapper — 场景语义 → 节拍表（节奏纪律的载体）+ comp.html 装配（纯函数）。

节奏纪律（onetake SKILL 硬规则，rhythm_report 逐条可测）：
  * 镜长差 ≥4×（cadence CV ≥ 0.25）——均分镜 = PPT；
  * 至少一段 ≥1.0s 的完全静止（rest 腿）+ 全片 ≥25% 静帧；
  * staccato 三连击声明为 cuts（probe 连续性豁免 + burst 腿）；
  * carry：header / hand / subject 卡贯穿全部边界（comp 内实现）。
"""

import copy
import json
import os

TEMPLATE_PATH = "template/cf_showcase.html"


def template_path() -> str:
    """合成模板绝对路径（以本包 __file__ 锚定，任意 cwd/部署形态都正确）。"""

    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_PATH)

# 节拍表（15s @30fps）。镜长：0.95/2.15/2.05/3.40/3.10/0.70/1.70 —— 差 ≥4×。
BEATS = {
    "hookIn": 0.12,
    "hookOut": 1.30,
    "headerIn": 1.05,
    "handIn": 1.90,
    "handOut": 12.45,
    "artIn": 1.30,
    "sweep": 3.45,
    "morphPixel0": 3.30,
    "morphPixel1": 3.60,
    "morphAnim0": 5.20,
    "morphAnim1": 5.80,
    "animIn": 5.80,
    "strike": 7.55,
    "animOut": 9.20,
    "morphEngine0": 9.20,
    "morphEngine1": 9.80,
    "engineHold0": 11.00,
    "engineHold1": 12.30,
    "engineOut": 12.30,
    "end": 13.20,
}

# 手的单一连续路径：入画 → 原画卡 → 指向重建扫描线 → 攻击轨迹（含点击）→ 预览窗（点击）→ 驻留 → 出画
HAND_KNOTS = [
    {"t": 1.90, "x": 2050, "y": 1200},
    {"t": 2.55, "x": 1140, "y": 930},
    {"t": 3.05, "x": 1140, "y": 930},
    {"t": 3.62, "x": 965, "y": 540},
    {"t": 4.30, "x": 1020, "y": 470},
    {"t": 5.60, "x": 760, "y": 520},
    {"t": 6.60, "x": 470, "y": 620},
    {"t": 7.30, "x": 390, "y": 760},
    {"t": 7.55, "x": 800, "y": 330},
    {"t": 7.90, "x": 800, "y": 330},
    {"t": 8.60, "x": 700, "y": 620},
    {"t": 9.90, "x": 1270, "y": 880},
    {"t": 10.40, "x": 1230, "y": 870},
    {"t": 12.45, "x": 1230, "y": 880},
    {"t": 12.80, "x": 2100, "y": 1250},
]
CLICKS = [7.55, 10.15]

RECTS = {
    "art": {"x": 560, "y": 130, "w": 800, "h": 800},
    "pixel": {"x": 560, "y": 130, "w": 800, "h": 800},
    "anim": {"x": 190, "y": 220, "w": 620, "h": 620},
    "engine": {"x": 610, "y": 170, "w": 700, "h": 700},
}

SHOTS = [0.0, 1.30, 3.45, 5.50, 9.20, 12.30, 12.55, 12.78, 13.01, 13.20]


def build_timeline(scene: dict, assets: dict, presentation: dict | None = None, duration: float = 15.0) -> dict:
    """→ 完整 CF 配置（注入 comp 的 window.CF）。纯函数、确定性。"""

    presentation = presentation or {}
    beats = dict(BEATS)
    beats["engineHold0"] = min(beats["engineHold0"], beats["engineHold1"] - 1.05)  # rest 腿 ≥1.0s
    hand = [dict(k) for k in HAND_KNOTS]
    stac = [[round(beats["end"] - 0.75 + i * 0.23, 2), word[0]] for i, word in enumerate(scene["stac"])]
    return {
        "meta": {"dur": round(duration, 3), "fps": 30, "seed": int(presentation.get("seed") or 7)},
        "tokens": scene["tokens"],
        "copy": scene["copy"],
        "beats": beats,
        "rects": copy.deepcopy(RECTS),
        "hand": hand,
        "clicks": list(CLICKS),
        "stac": stac,
        "cuts": [row[0] for row in stac],
        "assets": assets,
        "inFrame": {"subject": [beats["artIn"], beats["engineOut"], "whole"]},
    }


def render_comp(cf: dict, template: str) -> str:
    """CF 注入模板（唯一占位符 {{CF_JSON}}；模板其余部分逐字保留）。"""

    payload = json.dumps(cf, ensure_ascii=False, separators=(",", ":"))
    if "{{CF_JSON}}" not in template:
        raise ValueError("showcase 模板缺少 {{CF_JSON}} 占位符")
    return template.replace("{{CF_JSON}}", payload)


def shots_list(cf: dict) -> list[float]:
    """verify_promo --shots 的镜切清单（cadence 腿输入）。"""

    return list(SHOTS)


def rhythm_report(cf: dict) -> dict:
    """节奏自检（单测断言用）：镜长 CV、静止段、cuts 声明完整性。"""

    import numpy as np

    lengths = np.diff(np.array(SHOTS + [cf["meta"]["dur"]], dtype=float))
    cv = float(lengths.std() / max(1e-6, lengths.mean()))
    beats = cf["beats"]
    quiet = beats["engineHold0"] and (beats["engineHold1"] - beats["engineHold0"])
    return {
        "shot_lengths": [round(x, 3) for x in lengths.tolist()],
        "cadence_cv": round(cv, 3),
        "quiet_stretch_s": round(float(quiet), 3),
        "cuts_declared": cf["cuts"],
        "ratio_ge_4x": round(float(lengths.max() / max(1e-6, lengths.min())), 2),
    }
