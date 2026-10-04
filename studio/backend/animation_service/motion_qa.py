"""生成后自动质检（V3.5 三维量化标准的逐条产出落地）.

对**每一条真实生成的动画**（骨骼链/i2v 视频链）计算量化指标并分级：
  * 动作流畅度  —— motion_cv（能量变异，仅循环动作门控：跳跃抛物线的
    慢顶点快落地是天文学事实）、frozen_ratio（近静止相邻帧占比——呼吸
    顶点/蓄力段的低速帧是运动学事实，占比制判定）、mean_energy（骨骼链
    按动作分档下限，i2v 链尺度不同不设）
  * 时序/身份  —— temporal_sim（相邻帧 similarity overall，下限按循环
    0.90 / 一次性 0.65——合法大姿态会拉低逐帧相似度）、palette_sim_vs_f0
    （调色板对首帧漂移，i2v 常见劣化）
  * 细节还原  —— 源画标志色的 survival（帧中存在率）与 completeness
    （最佳帧纯色像素/源像素，**源图先缩到帧尺寸再计数**——否则分辨率
    缩放会被误判成细节丢失，实测 384/1024 面积比 0.151 的假阴性）

阈值全部来自实测校准（2026-10-04，夹具五动作 + 两条真实 i2v flash 片段）：
  夹具 frozen_ratio 0~0.083 / cv 0.18~1.45(一次性) / temporal 0.986+ /
  palette 0.97+；i2v temporal 0.947+ / palette 0.931+ / completeness 1.0。

质检是**增益项**：任何异常返回 None 并绝不阻塞生成。grade ∈
pass/warn/fail，issues 为可读中文（前端徽章与人工复核入口）。
"""

import io
import math

import numpy as np
from PIL import Image

from artgen.style import similarity_rgba

# ── 阈值（实测校准，改动需同步 motion_baseline 校准记录）─────────────────
FROZEN_ENERGY = 0.06  # 相邻帧能量低于此 = 近静止对
ALL_STATIC_ENERGY = 0.05  # 全循环平均能量低于此 = 完全冻结（硬失败）
FROZEN_WARN = 0.35
FROZEN_FAIL = 0.70
CV_WARN = 0.85  # 仅 idle/walk/run（jump 抛物线慢顶点天然高 cv）
CV_FAIL = 1.60
TEMPORAL_FLOOR = {"cyclic": 0.90, "burst": 0.65}
PALETTE_WARN = 0.88
PALETTE_FAIL = 0.85
SURVIVAL_WARN = 0.70
COMPLETENESS_WARN = 0.70
COMPLETENESS_FAIL = 0.40
# 逐色最小值硬门：均值口径下丢一件小面积标志物（武器金色 288px）会被
# 三件大件（甲蓝 ~1165px）摊薄成 0.75 蒙混——任一标志色在**所有帧**中
# 几乎消失（最佳帧完整度 <0.15）即 fail，<0.45 warn
COMPLETENESS_MIN_WARN = 0.45
COMPLETENESS_MIN_FAIL = 0.15
# 骨骼链分动作能量下限（实测夹具：idle 1.12 walk 2.88 run 3.56 attack 1.57 jump 4.52，
# 下限留 ~4× 余量；i2v 链画面含背景微动，尺度不同不设）
ENERGY_FLOOR = {"idle": 0.25, "walk": 0.80, "run": 1.20, "attack": 0.40, "jump": 1.00}
_CYCLIC_ACTIONS = ("idle", "walk", "run")


def _detail_palette(source_img):
    """源画显著色簇（饱和度×面积 top-4，剔除边缘背景色）。"""
    from collections import Counter

    quant = source_img.quantize(colors=16).convert("RGB")
    counts = Counter(quant.getdata())
    border = [quant.getpixel((x, 0)) for x in range(0, source_img.width, 8)] + [
        quant.getpixel((0, y)) for y in range(0, source_img.height, 8)
    ]
    border_set = set(border)
    ranked = []
    for color, count in counts.items():
        if color in border_set:
            continue
        saturation = max(color) - min(color)
        ranked.append((saturation * math.sqrt(count), saturation, color))
    ranked.sort(reverse=True)
    return [color for _, sat, color in ranked[:4] if sat >= 30]


def post_validate(frames_rgba, source_bytes=None, action="walk", chain="skeletal"):
    """-> {"grade", "metrics", "issues"}；frames_rgba 为 [(w,h,rgba)]。"""

    if not frames_rgba or len(frames_rgba) < 2:
        return None
    profile = [
        np.asarray(Image.frombytes("RGBA", (w, h), bytes(rgba)), dtype=np.float32)
        for w, h, rgba in frames_rgba
    ]
    size = (profile[0].shape[1], profile[0].shape[0])

    def _sim(a, b):
        return similarity_rgba(
            (a.shape[1], a.shape[0], bytes(a.astype(np.uint8).tobytes())),
            (b.shape[1], b.shape[0], bytes(b.astype(np.uint8).tobytes())),
        )

    energies = [
        float(abs(profile[i] - profile[(i + 1) % len(profile)]).mean())
        for i in range(len(profile))
    ]
    mean_energy = sum(energies) / len(energies)
    frozen_ratio = sum(1 for e in energies if e < FROZEN_ENERGY) / len(energies)
    motion_cv = (
        float(np.std(energies) / mean_energy) if mean_energy > 1e-6 else 0.0
    )
    temporal_values = [_sim(profile[i], profile[i - 1])["overall"] for i in range(1, len(profile))]
    temporal_sim = sum(temporal_values) / len(temporal_values)
    identity_values = [
        _sim(profile[0], frame)["palette"]
        for frame in profile[:: max(1, len(profile) // 6)]
    ]
    palette_sim = sum(identity_values) / len(identity_values)

    metrics = {
        "mean_energy": round(mean_energy, 3),
        "motion_cv": round(motion_cv, 3),
        "frozen_ratio": round(frozen_ratio, 3),
        "temporal_sim": round(temporal_sim, 4),
        "palette_sim": round(palette_sim, 4),
    }

    issues = []
    grade = "pass"

    def _raise(level, text):
        nonlocal grade
        issues.append(text)
        if level == "fail" or grade == "fail":
            grade = "fail"
        elif level == "warn":
            grade = "warn"

    if mean_energy < ALL_STATIC_ENERGY:
        _raise("fail", "画面完全静止（平均帧间能量 {:.3f}），动画疑似冻结".format(mean_energy))
    elif frozen_ratio > FROZEN_FAIL:
        _raise("fail", "疑似卡帧：{:.0f}% 的相邻帧几乎静止（阈值 {:.0f}%）".format(
            frozen_ratio * 100, FROZEN_FAIL * 100))
    elif frozen_ratio > FROZEN_WARN:
        _raise("warn", "低速帧偏多：{:.0f}% 的相邻帧近静止（呼吸/蓄力属正常，确认是否有顿挫）".format(
            frozen_ratio * 100))

    cyclic = action in _CYCLIC_ACTIONS
    if cyclic and motion_cv > CV_FAIL:
        _raise("fail", "节奏紊乱：运动能量变异系数 {:.2f}（循环动作应匀称）".format(motion_cv))
    elif cyclic and motion_cv > CV_WARN:
        _raise("warn", "节奏欠匀：运动能量变异系数 {:.2f}".format(motion_cv))

    temporal_floor = TEMPORAL_FLOOR["cyclic" if cyclic else "burst"]
    if temporal_sim < temporal_floor:
        _raise("warn", "帧间跳动：相邻帧相似度 {:.3f} 低于 {:.2f} 下限".format(temporal_sim, temporal_floor))

    if palette_sim < PALETTE_FAIL:
        _raise("fail", "色彩漂移：相对首帧调色板相似度 {:.3f}（应≥{:.2f}）".format(palette_sim, PALETTE_FAIL))
    elif palette_sim < PALETTE_WARN:
        _raise("warn", "轻微色彩漂移：相对首帧调色板相似度 {:.3f}".format(palette_sim))

    if chain == "skeletal":
        floor = ENERGY_FLOOR.get(action)
        if floor is not None and mean_energy < floor:
            _raise("warn", "动作幅度偏低：平均能量 {:.2f} 低于 {} 建议下限 {:.2f}".format(
                mean_energy, action, floor))

    if source_bytes:
        try:
            source_img = Image.open(io.BytesIO(source_bytes)).convert("RGB").resize(
                size, Image.LANCZOS
            )
            palette = _detail_palette(source_img)
            source_arr = np.asarray(source_img, dtype=np.float32)
            survivals, completions = [], []
            for color in palette:
                target = np.array(color, dtype=np.float32)
                source_hits = int(
                    (abs(source_arr - target[None, None, :]).max(axis=2) < 40).sum()
                )
                presence = 0
                best_ratio = 0.0
                for arr in profile:
                    close = (
                        abs(arr[..., :3] - target[None, None, :]).max(axis=2) < 40
                    ) & (arr[..., 3] > 200)
                    count = int(close.sum())
                    if count >= max(6, int(0.02 * source_hits)):
                        presence += 1
                        best_ratio = max(best_ratio, min(1.0, count / max(1, source_hits)))
                survivals.append(presence / len(profile))
                completions.append(best_ratio)
            survival = sum(survivals) / len(survivals) if survivals else 1.0
            completeness = (
                sum(completions) / len(completions) if completions else 1.0
            )
            completeness_min = min(completions) if completions else 1.0
            metrics["detail_survival"] = round(survival, 3)
            metrics["detail_completeness"] = round(completeness, 3)
            metrics["detail_completeness_min"] = round(completeness_min, 3)
            if survival < SURVIVAL_WARN:
                _raise("warn", "标志色存活率低：{:.0f}%（衣物/武器颜色在部分帧中消失）".format(
                    survival * 100))
            if completeness < COMPLETENESS_FAIL:
                _raise("fail", "细节大量丢失：标志色完整度 {:.2f}（应≥{:.2f}）".format(
                    completeness, COMPLETENESS_FAIL))
            elif completeness < COMPLETENESS_WARN:
                _raise("warn", "细节偏少：标志色完整度 {:.2f}".format(completeness))
            if completeness_min < COMPLETENESS_MIN_FAIL:
                _raise("fail", "标志细节丢失：某个标志色的最佳帧完整度仅 {:.2f}（疑似武器/"
                    "配饰被抹掉或变色）".format(completeness_min))
            elif completeness_min < COMPLETENESS_MIN_WARN:
                _raise("warn", "某个标志色完整度偏低：{:.2f}".format(completeness_min))
        except Exception:  # noqa: BLE001 - 细节还原是增益项
            pass

    return {"grade": grade, "metrics": metrics, "issues": issues}
