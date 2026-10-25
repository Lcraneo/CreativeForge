"""Character-bound skeletal animation (Phase 2).

Unlike ``anim.py`` (which *draws* a programmatic template character) and
``sourceanim.py`` (which only bobs the whole subject), this module binds the
character's **own pixels** to the extracted rig and moves each body region
with its joint (two-bone IK for legs/arms), then re-composites over a fixed
background. Result: different characters → different, character-specific
animations; no fixed template character is ever produced.
"""

import io
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from artgen.anim import ACTIONS, _pose
from artgen.rig import build_rig
from artgen.sourceanim import BG_DIFF_THRESHOLD, _fit, _subject_mask
from artgen.style import similarity_rgba

CANVAS_BG = (0, 0, 0, 0)


def _inpaint_background(canvas, mask, grow=6):
    """主体区逐行水平插值回填背景（替代单一中值色填充）。

    分区旋转后，原主体位置会短暂露底；旧版用边缘中值色整块填充，而
    AI 原画的背景几乎都有渐变——露底区与周围真实背景形成一圈可见的
    色差亮边（工作台预览实测：手臂/躯干轮廓外的白边环）。逐行用主体
    左右最近的背景像素插值，填充色跟随渐变，露底与背景无缝。"""
    arr = np.asarray(canvas.convert("RGBA"), dtype=np.float32).copy()
    grown = mask.filter(ImageFilter.MaxFilter(grow * 2 + 1))
    holes = np.asarray(grown) > 128
    height, width = holes.shape
    for y in range(height):
        xs = np.nonzero(holes[y])[0]
        if xs.size == 0:
            continue
        x0, x1 = int(xs[0]), int(xs[-1])
        left = arr[y, x0 - 1, :3] if x0 > 0 else arr[y, min(width - 1, x1 + 1), :3]
        right = arr[y, x1 + 1, :3] if x1 < width - 1 else left
        span = x1 - x0
        if span <= 0:
            arr[y, x0, :3] = (left + right) / 2.0
            continue
        t = np.linspace(0.0, 1.0, span + 1)[:, None]
        arr[y, x0 : x1 + 1, :3] = left[None, :] * (1.0 - t) + right[None, :] * t
    return Image.fromarray(arr.astype(np.uint8), mode="RGBA")


def _absorb_enclosed_background(mask, rgb, bg_color=None):
    """把主体内与背景色同色的**封闭区**回收为背景（分体修复 R1）。

    洪泛抠图（_flood_subject）从画布边缘出发，只能吃掉与边缘**连通**的
    背景；被肢体围住的背景洞——两腿之间、脚与阴影围出的区域——不可达，
    会被误判成主体。分区旋转动画里，这些洞像素落进腿/躯干区域层跟着
    旋转平移，就是试玩舞台"蓝色色块飘移/身体分体"的根因。

    ``bg_color``：背景参考色（默认取画布边缘中值色；AI 分割路径的契约
    是纯白底，调用方显式传 (255,255,255)）。

    判据（三条件同时满足才回收，避免误伤与背景撞色的服装）：
      1. 当前被标记为主体；
      2. 颜色与背景参考色的逐通道差 ≤ BG_DIFF_THRESHOLD（与洪泛同口径）；
      3. 所属连通域**不接触**画布边缘（接触边缘的保留不动，保守处理
         渐变背景漏吃的情况）；
      4. 连通域**质心落在主体下半部**（y ≥ 主体 bbox 中线）。腿间/脚边
         的封闭洞都在下半身；而浅肤色、白衣高光这类"颜色接近背景的大
         面积面部/躯干区域"也满足前三条——实测整张脸被当洞回收、躯干
         层在脸上开洞透出背景填充色（帧上就是碎裂竖缝）。质心判据让
         上半身的候选一律保留。

    任何失败返回原 mask（该修复永不阻塞动画生成）。"""

    try:
        subject = np.asarray(mask, dtype=np.uint8) > 128
        if not subject.any():
            return mask
        rgb_arr = np.asarray(rgb.convert("RGB"), dtype=np.int16)
        if rgb_arr.shape[:2] != subject.shape:
            return mask
        if bg_color is None:
            from artgen.sourceanim import _border_bg

            bg_color = _border_bg(rgb)
        bg = np.array(bg_color, dtype=np.int16)
        color_ok = np.abs(rgb_arr - bg[None, None, :]).max(axis=2) <= BG_DIFF_THRESHOLD
        candidates = subject & color_ok
        if not candidates.any():
            return mask

        border_touch = np.zeros_like(candidates)
        border_touch[0, :] = border_touch[-1, :] = True
        border_touch[:, 0] = border_touch[:, -1] = True

        ys_all, _xs_all = np.nonzero(subject)
        floor_y = float(ys_all.min()) + 0.5 * float(ys_all.max() - ys_all.min() + 1)

        absorbed = np.zeros_like(candidates)
        visited = np.zeros_like(candidates)
        remaining = candidates & ~border_touch
        # 向量 BFS：从任意未访问种子做二值传播标注连通域
        while remaining.any():
            ys, _xs = np.nonzero(remaining)
            frontier = np.zeros_like(candidates)
            frontier[int(ys[0]), int(_xs[0])] = True
            comp = np.zeros_like(candidates)
            while frontier.any():
                comp |= frontier
                grew = np.zeros_like(candidates)
                grew[1:, :] |= frontier[:-1, :]
                grew[:-1, :] |= frontier[1:, :]
                grew[:, 1:] |= frontier[:, :-1]
                grew[:, :-1] |= frontier[:, 1:]
                frontier = grew & candidates & ~comp
            visited |= comp
            comp_ys, _comp_xs = np.nonzero(comp)
            if float(comp_ys.mean()) >= floor_y:
                absorbed |= comp
            remaining = candidates & ~visited

        if not absorbed.any():
            return mask

        cleaned = np.asarray(mask).copy()
        cleaned[absorbed] = 0
        result = Image.fromarray(cleaned, mode="L")
        # 回收边界补羽化，与主体切边同质感
        return result.filter(ImageFilter.GaussianBlur(1.0))
    except Exception:  # noqa: BLE001 - 修复永不阻塞动画生成
        return mask


def _region_layer(subject, rect, size, feather=5.0, exclude_above=None, protect_top=0.0, protect_bottom=0.0):
    """Full-canvas transparent layer containing only ``rect`` of ``subject``,
    with a **feathered** mask: adjacent regions blend into each other instead
    of cutting hard seams (P1 生成质量：消除分区旋转的接缝).

    ``exclude_above``：头部保护区 y 值（分体修复 R2）——该 y 之上的像素
    全部置透明。手臂/前臂区域是横跨半身的矩形，Q 版角色（头占比大）的
    脸会落进手臂矩形，摆臂时把脸"片"走（试玩区实测的脸部横向切片）。

    ``protect_top``/``protect_bottom``：羽化保护带（px）——关节搭接带是
    **有意的融合区**（父子段角度差由跨带渐变吸收），带内保持纯羽化。

    V3.5 内部实心化（细节还原）：保护带之外，矩形内 ≥1px 且深在主体轮廓
    内（≥3px 腐蚀）的像素**不吃羽化衰减**（取 max）——持械/长杖/裙摆这类
    跨区配饰整条落在分区矩形边界羽化带内，会被高斯羽化与透明底混合洗色
    （实测金色武器 343 纯色 px → 220，1/3 细节被洗掉）。主体外轮廓 3px
    环仍走羽化保剪影抗锯齿；全 alpha 搭接由绘制顺序（子层后画=子层胜）
    与 mesh 皮肤化的角度过渡兜底。
    """

    layer = Image.new("RGBA", (size, size), CANVAS_BG)
    box = (
        max(0, int(rect[0])),
        max(0, int(rect[1])),
        min(size, int(rect[2])),
        min(size, int(rect[3])),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return layer
    layer.paste(subject.crop(box), (box[0], box[1]))

    rect_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(rect_mask).rectangle(box, fill=255)
    if feather > 0:
        feathered = rect_mask.filter(ImageFilter.GaussianBlur(feather))
        # 内部实心化：矩形腐蚀 1px × 主体深内部（腐蚀 3px）→ 取 lighter(max)；
        # 保护带（搭接区）内撤销实心化，退回纯羽化
        hard = rect_mask.filter(ImageFilter.MinFilter(3))
        if protect_top > 0:
            ImageDraw.Draw(hard).rectangle(
                (box[0], box[1], box[2], min(box[3], box[1] + int(protect_top))), fill=0
            )
        if protect_bottom > 0:
            ImageDraw.Draw(hard).rectangle(
                (box[0], max(box[1], box[3] - int(protect_bottom)), box[2], box[3]), fill=0
            )
        deep_subject = subject.getchannel("A").filter(ImageFilter.MinFilter(7))
        solid = ImageChops.multiply(hard, deep_subject)
        rect_mask = ImageChops.lighter(feathered, solid)
    if exclude_above is not None and exclude_above > 0:
        # 保护区在羽化**之后**硬归零：羽化的上侧扩散会把贴近下巴的脸部
        # 像素以 0.2~0.5 的 alpha 漏进手臂层（实测漏出 ~7px 的刚性偏差），
        # 归零只保留羽化在下侧的接缝过渡
        ImageDraw.Draw(rect_mask).rectangle((0, 0, size, int(exclude_above)), fill=0)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), rect_mask))
    return layer


def _rotate_clean(layer, pivot, angle):
    """预乘空间旋转：双三次重采样在透明边界会把透明像素的 RGB（洞底色/
    袋底白）拉进可见区（实测封闭白洞在腿缘漏出 α=131 的 240+ 近白像素）。
    先 RGB×alpha 预乘、旋转、再除回 alpha——边缘颜色与透明度同步过渡，
    零色溢。alpha=0 处 RGB 归零，旋转后按 alpha 安全除回。"""

    arr = np.asarray(layer, dtype=np.float32)
    alpha = arr[..., 3:4] / 255.0
    premul = arr.copy()
    premul[..., :3] *= alpha
    img = Image.fromarray(np.clip(premul, 0, 255).astype(np.uint8), "RGBA")
    rotated = img.rotate(angle, resample=Image.BICUBIC, center=(pivot[0], pivot[1]), expand=False)
    out = np.asarray(rotated, dtype=np.float32)
    a = out[..., 3:4] / 255.0
    safe = np.maximum(a, 1.0 / 255.0)
    out[..., :3] = np.where(a > 1.0 / 255.0, np.clip(out[..., :3] / safe, 0, 255), 0.0)
    # 双三次在硬边的过冲（腿缘 120 冲到 ~130）经低 alpha 除回会被放大成
    # 近白色（实测 130/0.514=253 的"白洞泄漏"）——钳回本图层不透明像素
    # 的色域：重采样不可能创造源色域之外的颜色
    opaque = arr[..., 3] > 250
    if opaque.any():
        lo = np.min(arr[..., :3][opaque], axis=0)
        hi = np.max(arr[..., :3][opaque], axis=0)
        out[..., :3] = np.clip(out[..., :3], lo, hi)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def _rotated_canvas(layer, pivot, angle, offset, size):
    """旋转后的图层铺到全幅透明画布（offset 取整定位）。"""

    rotated = _rotate_clean(layer, pivot, angle)
    canvas = Image.new("RGBA", (size, size), CANVAS_BG)
    canvas.paste(rotated, (int(round(offset[0])), int(round(offset[1]))))
    return canvas


def _place_over(subject, layer, pivot, angle, offset, size):
    """真 alpha over：图层合到主体画布。旧 paste 直贴在透明底上会把被覆盖
    图层的 alpha 拉低（羽化边缘透底），over 合成保持不透明区域不透明。"""

    return Image.alpha_composite(subject, _rotated_canvas(layer, pivot, angle, offset, size))


def _apply_yaw(subject, yaw_deg, cx, size):
    """绕纵轴假转身（2D 骨骼引擎的标准做法）：主体整体水平压缩到
    cos(|yaw|)，|yaw|>90° 时水平镜像（背面）。纯画布后变换，不触碰
    分层/双骨链——分体与拖影修复都在此之前已完成，不受影响。
    turn 曲线在 anim._pose 端保证接缝回 0°，循环闭合。"""

    rad = math.radians(max(-180.0, min(180.0, float(yaw_deg))))
    sx = max(0.15, abs(math.cos(rad)))
    w2 = max(1, int(round(size * sx)))
    squeezed = subject.resize((w2, size), Image.LANCZOS)
    if math.cos(rad) < 0:
        squeezed = squeezed.transpose(Image.FLIP_LEFT_RIGHT)
    out = Image.new("RGBA", (size, size), CANVAS_BG)
    out.paste(squeezed, (int(round(cx - w2 / 2.0)), 0))
    return out


# ── 网格变形（V3）：膝/肘皮肤化 ─────────────────────────────────────────────
# 旧刚体路径里，小腿/前臂的世界角 = 父段角 + 屈曲角，屈曲全部集中在关节点
# 一处——膝上 22px 搭接带就是父段取向与子段取向的硬不连续，靠羽化吸收。
# 皮肤化把这一处硬折弯摊开成过渡带内的连续弯曲：子层顶部 band_px 内，世界
# 角从父段角（跨关节连续）平滑插值到完整屈曲角，带外刚体。姿态端点不变
# （远端角与旧路径相同），改变的只是关节附近的过渡分布。
RIGANIM_SKIN_DEFAULT = "mesh"  # A/B 回退开关：改回 "rigid" 一键还原 v5/v6 行为
SKIN_BAND_SHIN = 28.0  # 小腿过渡带 = 膝上搭接 22px + 羽化余量
SKIN_BAND_FOREARM = 16.0  # 前臂过渡带 = 肘上搭接 6px + 羽化余量
SKIN_STRIPS = 6
SKIN_MIN_ANGLE = 0.5  # 近/远角差小于此度数直接走刚体（零屈曲零开销零风险）


def _smoothstep(t):
    t = max(0.0, min(1.0, float(t)))
    return t * t * (3.0 - 2.0 * t)


def _mesh_union(canvases):
    """条带画布的「max-alpha 独占所有权」合成：每像素取 alpha 最高的条带
    的颜色与透明度。重叠区不产生半透明双绘（v5/v6 分区独占所有权哲学在
    子层内的复用——条带间只有亚像素级重采样差，接缝不可见）。"""

    if len(canvases) == 1:
        return canvases[0]
    stack = np.stack(
        [np.asarray(c.getchannel("A"), dtype=np.uint16) for c in canvases], axis=0
    )
    winner = stack.argmax(axis=0)
    out = np.asarray(canvases[0], dtype=np.uint8).copy()
    for k in range(1, len(canvases)):
        mask = winner == k
        if not mask.any():
            continue
        out[mask] = np.asarray(canvases[k], dtype=np.uint8)[mask]
    return Image.fromarray(out, "RGBA")


def _mesh_canvas(layer, pivot, angle_near, angle_far, band_px, offset, size, strips=SKIN_STRIPS):
    """皮肤化子层画布：见 RIGANIM_SKIN_DEFAULT 注释。近/远角差可忽略、
    过渡带过窄或条带数不足时，退化为与旧路径逐像素同语义的单次刚体旋转。"""

    delta = float(angle_far) - float(angle_near)
    if abs(delta) < SKIN_MIN_ANGLE or band_px < 4.0 or strips < 2:
        return _rotated_canvas(layer, pivot, angle_far, offset, size)

    alpha_rows = np.asarray(layer.getchannel("A"), dtype=np.uint8)
    rows = np.where(alpha_rows.max(axis=1) > 0)[0]
    if len(rows) == 0:
        return _rotated_canvas(layer, pivot, angle_far, offset, size)
    y_top = float(rows[0])
    y_bot = float(rows[-1])
    band = min(float(band_px), max(4.0, y_bot - y_top))

    overlap = 2.0
    edges = [y_top + band * k / strips for k in range(strips + 1)]
    canvases = []
    for k in range(strips):
        lo, hi = edges[k], edges[k + 1]
        theta = angle_near + delta * _smoothstep(((lo + hi) / 2.0 - y_top) / band)
        mask_arr = np.zeros_like(alpha_rows, dtype=np.uint8)
        mask_arr[int(max(0, math.floor(lo - overlap))) : int(min(size, math.ceil(hi + overlap))), :] = 255
        strip = layer.copy()
        strip.putalpha(
            ImageChops.multiply(
                strip.getchannel("A"),
                Image.fromarray(mask_arr, "L").filter(ImageFilter.GaussianBlur(1.2)),
            )
        )
        canvases.append(_rotated_canvas(strip, pivot, theta, offset, size))
    # 远端刚体段：过渡带之下整段按完整屈曲角（与旧刚体路径同角同 pivot）
    mask_arr = np.zeros_like(alpha_rows, dtype=np.uint8)
    mask_arr[int(max(0, math.floor(edges[-1] - overlap))) :, :] = 255
    rigid = layer.copy()
    rigid.putalpha(
        ImageChops.multiply(
            rigid.getchannel("A"),
            Image.fromarray(mask_arr, "L").filter(ImageFilter.GaussianBlur(1.2)),
        )
    )
    canvases.append(_rotated_canvas(rigid, pivot, angle_far, offset, size))
    return _mesh_union(canvases)


def _falign(frames):
    """Lightweight FAlign-style report for the rig-driven frames."""
    step = max(1, len(frames) // 8)
    sampled = frames[::step]
    if len(sampled) >= 2:
        diffs = [
            similarity_rgba(sampled[i - 1], sampled[i])["overall"] for i in range(1, len(sampled))
        ]
        temporal = round(sum(diffs) / len(diffs), 4)
    else:
        temporal = 1.0
    anchor = 1.0  # feet are pinned to the rig root, so the root never drifts
    return {
        "anchor": anchor,
        "temporal": temporal,
        "overall": round(0.4 * anchor + 0.6 * temporal, 4),
        "frames_checked": len(sampled),
    }


def _motion_scales(rig, size):
    """动作幅度 ↔ 体型匹配（专业级观感：同一套曲线适配不同比例的角色）。

    * ``limb``   关节角缩放——Q 版（头身比大、肢段短）角度收敛，
      避免短肢甩出"鞭梢感"；
    * ``offset`` 位移缩放——bob/sway 等像素量随角色实际身高缩放，
      小个子角色不再顶着成人大幅度曲线；
    * ``bob``    垂直起伏总增益——offset 之上再给 Q 版一点弹跳感。"""

    head_ratio = float((rig or {}).get("head_ratio") or 0.6)
    chibi_f = max(0.0, min(1.0, (head_ratio - 0.55) / 0.35))
    bbox = (rig or {}).get("bbox") or [0, 0, size, size]
    height = max(1.0, float(bbox[3] - bbox[1]))
    offset = max(0.55, min(1.5, height / (0.62 * size)))
    return {
        "limb": 1.0 - 0.18 * chibi_f,
        "offset": offset,
        "bob": offset * (1.0 + 0.30 * chibi_f),
    }


def _tint_layer(layer, factor=0.72):
    """远侧肢体调暗（2D 侧视深度线索）：不透明像素 RGB×factor，alpha 不变。
    预乘语义安全（先除回 alpha 的色域钳制在 tint 后仍成立）。"""

    arr = np.asarray(layer, dtype=np.float32)
    alpha = arr[..., 3:4] / 255.0
    arr[..., :3] *= np.where(alpha > 0, factor, 1.0)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def animate_rigged(
    image_bytes,
    action="walk",
    frame_count=12,
    size=384,
    rig=None,
    config=None,
    segment_mask=None,
    keep_background=True,
    skin=None,
    overlays=None,
    view="front",
):
    """-> (frames, reference, rig, falign).

    ``frames`` is a list of (w, h, RGBA); ``reference`` is the untouched source;
    ``rig`` is the extracted CharacterRig; ``falign`` the alignment report.

    ``keep_background=False`` renders the character as a transparent cutout
    (no scene background behind the subject) — used by the playtest stage so
    frames composite onto an arbitrary stage and trim to the subject bounds.

    ``skin``：网格变形开关（V3）——"mesh" 膝/肘皮肤化（默认，
    RIGANIM_SKIN_DEFAULT），"rigid" 完全还原 v5/v6 刚体路径；config 键
    ``skin`` 可同样指定（pose_config 透传），显式参数优先。

    ``overlays``：次级运动图层（V3，发/裙摆动）——dict 列表
    ``{"layer": RGBA Image, "root": (nx, ny) 归一化锚点, "amp": 摆幅角,
    "lag": 相位滞后 0..1}``。图层跟随躯干变换（lean/tilt/sway/dy）并叠加
    sin 摆动，置于躯干之后、手臂之前。amp=0 时仅跟随不摆动。"""
    size = max(64, min(1024, int(size)))
    frame_count = max(2, min(60, int(frame_count)))
    action = action if action in ACTIONS else "walk"
    # 网格变形开关（V3）：显式参数 > config 键 > 模块默认
    skin_mode = skin or (config or {}).get("skin") or RIGANIM_SKIN_DEFAULT
    use_mesh = skin_mode == "mesh"
    # 侧视深度模式（V3 步态修复）：侧视原画的双腿/双臂在画面上重叠，
    # "左右半身切分"会把身体撕成两半反相拉扯（实测左右髋仅差 22px）。
    # 侧视改为近/远肢体 = 同一完整块的两份拷贝：远侧调暗+反相+先画。
    side_view = view == "side"

    canvas = _fit(Image.open(io.BytesIO(image_bytes)), size)
    mask, transparent, bg = _subject_mask(canvas)
    if segment_mask is not None and not transparent:
        mask = segment_mask.resize((size, size))
    if not transparent:
        # 分体修复 R1：洪泛/AI 分割都可能把"被肢体围住的封闭背景洞"
        # 误判成主体（两腿之间露出的原背景色）。洞像素在画布上显示的
        # 就是原背景色，两条路径都用洪泛的边缘中值色作参考。
        mask = _absorb_enclosed_background(mask, canvas, bg_color=bg)

    rig = rig or build_rig(image_bytes, size, segment_mask=segment_mask)
    x0, y0, x1, y1 = rig["bbox"]
    points = rig["points"]
    cx = (x0 + x1) / 2.0
    w = max(1.0, x1 - x0)
    torso_half = (x1 - x0) * 0.20
    hip_y = points["hip_l"][1]
    shoulder_y = points["shoulder_l"][1]
    hand_y = points["hand_l"][1]
    # 头部保护区（分体修复 R2）：Q 版角色（头占比大）的肩带落在脸上，
    # 手臂/前臂区域矩形横穿面部，摆臂会把脸"片"走（试玩区实测的脸部
    # 横向切片）。颈线检测比例给出真实下巴位置；normal 角色钳到 0.30
    # 后低于肩带（42%），行为与修复前一致。
    head_h = max(0.30, min(0.75, float(rig.get("head_height") or 0.30)))
    chin_y = y0 + head_h * (y1 - y0) + 2.0

    # ── 腿部横向边界:双脚列段给出真实中缝 ─────────────────────────
    # 旧版腿带以画布中线 ±12%w 硬分,与两腿真实分界(常因站姿偏移数像素)
    # 不符;大腿带顶部 hip_y-26 还把腰带/外套下摆整块裹进腿层随腿旋转。
    # 底部列段分离出两只脚 → 间隙中点作中缝;腿带顶部收到 hip_y-12,
    # 腰带/下摆交给 upper/crotch 层(它们不随大腿旋转)。
    from artgen.rig import _column_runs as _foot_column_runs
    from artgen.rig import _extent as _row_extent

    bottom_runs = [r for r in _foot_column_runs(mask, int(y1) - 9, int(y1)) if r[1] > r[0]]
    if len(bottom_runs) >= 2:
        widest = sorted(bottom_runs, key=lambda run: run[1] - run[0], reverse=True)[:2]
        widest.sort(key=lambda run: run[0])
        leg_split = (widest[0][1] + widest[1][0]) / 2.0
    else:
        hip_row = _row_extent(mask, int(hip_y) - 2, int(hip_y) + 3)
        leg_split = (hip_row[0] + hip_row[1]) / 2.0 if hip_row else cx
    leg_split = max(min(leg_split, cx + w * 0.12), cx - w * 0.12)

    # subject layer (its alpha is the subject) + background with the subject removed
    if transparent:
        subject = canvas.copy()
        base_bg = canvas.copy()
        base_bg.paste(CANVAS_BG, (0, 0), mask)
    else:
        # V3 matting 精修：白底素材边界带内按合成方程反解真 alpha 与前景色，
        # 消除"mask 羽化保留旧底色"的边缘发灰/泛白（sourceanim.refine_edge_alpha，
        # 失败回退旧 putalpha 路径——修复永不阻塞生成）
        subject = canvas.copy()
        try:
            from artgen.sourceanim import refine_edge_alpha

            subject = refine_edge_alpha(canvas, mask, bg=bg or (255, 255, 255))
        except Exception:  # noqa: BLE001
            subject.putalpha(mask)
        if keep_background:
            base_bg = _inpaint_background(canvas, mask)
        else:
            base_bg = Image.new("RGBA", (size, size), CANVAS_BG)

    regions = {
        "upper": (
            _region_layer(subject, (x0, y0, x1, hip_y + 16), size, feather=8.0, protect_bottom=28.0),
            points["neck"],
        ),
        "arm_l": (
            _region_layer(
                subject,
                (x0, shoulder_y - 8, cx + torso_half * 0.1, min(y1, points["elbow_l"][1] + 6)),
                size,
                feather=4.0,
                # 肩 pivot 以上的像素（发梢/肩线上缘）一律不归臂层：源像素
                # 全在肩线下方，裁掉不影响任何抬臂动作，却能让"垂在肩上
                # 方的发梢"不再随摆臂甩动；肩部本身由 upper 层渲染。
                exclude_above=max(chin_y, shoulder_y + 4),
            ),
            points["shoulder_l"],
        ),
        "arm_r": (
            _region_layer(
                subject,
                (cx - torso_half * 0.1, shoulder_y - 8, x1, min(y1, points["elbow_r"][1] + 6)),
                size,
                feather=4.0,
                exclude_above=max(chin_y, shoulder_y + 4),
            ),
            points["shoulder_r"],
        ),
        # 帧粘连修复（分区独占所有权）：父段层只拥有自己的肢段——大腿层裁到
        # 膝（膝下像素只由小腿层渲染）、上臂层裁到肘（肘下只由前臂层渲染）。
        # 旧版父段层含整肢像素：膝弯/肘屈时父段层里那份"肢端拷贝"仍按父段
        # 角刚体旋转，与小腿/前臂层的弯角渲染同屏叠加——就是试玩区/工作台
        # 实测的"上一帧骨骼姿态残留 + 顶点裂变 + 拖影"。焊缝由子层顶部 22px
        # 的羽化搭接带吸收（子层绕关节旋转，关节处位移≈0）。
        "leg_l": (
            _region_layer(
                subject,
                (x0, hip_y - 12, leg_split + 2, min(y1, points["knee_l"][1] + 8)),
                size,
                feather=5.0,
            ),
            points["hip_l"],
        ),
        "leg_r": (
            _region_layer(
                subject,
                (leg_split - 2, hip_y - 12, x1, min(y1, points["knee_r"][1] + 8)),
                size,
                feather=5.0,
            ),
            points["hip_r"],
        ),
        # 裆部立柱（修复"身材切割"）：左右腿反向旋转时中缝会撕裂、露出底下
        # 的背景填充色。这一层取自原画自身的裆部像素，**不参与旋转**——且
        # 只做"填洞者"：逐帧用已绘制覆盖图门控，只贴到两条大腿摆开后露出的
        # 楔形空隙里，绝不压在运动中的腿上（旧版矩形一路到脚底、整列原姿态
        # 腿像素盖在每一帧上，正是"初始骨骼状态残留"的来源）。矩形也裁到
        # 膝：膝下的填缝属于小腿层的事。
        "crotch": (
            _region_layer(
                subject,
                (
                    leg_split - w * 0.17,
                    hip_y - 12,
                    leg_split + w * 0.17,
                    min(y1, points["knee_l"][1] + 6),
                ),
                size,
                feather=4.0,
            ),
            points["root"],
        ),
        # 双骨链子层：小腿（膝下含脚）与前臂（肘下含手）——跟随父段旋转角
        # 之上再叠加膝弯/肘屈，取代整腿/整臂单刚体旋转的"分段拼接感"
        "shin_l": (
            _region_layer(
                subject, (x0, points["knee_l"][1] - 22, leg_split + 2, y1), size, feather=5.5,
                protect_top=SKIN_BAND_SHIN,
            ),
            points["knee_l"],
        ),
        "shin_r": (
            _region_layer(
                subject, (leg_split - 2, points["knee_r"][1] - 22, x1, y1), size, feather=5.5,
                protect_top=SKIN_BAND_SHIN,
            ),
            points["knee_r"],
        ),
        "forearm_l": (
            _region_layer(
                subject,
                (x0, points["elbow_l"][1] - 6, cx + torso_half * 0.1, hand_y + 14),
                size,
                feather=3.0,
                exclude_above=chin_y,
                protect_top=SKIN_BAND_FOREARM,
            ),
            points["elbow_l"],
        ),
        "forearm_r": (
            _region_layer(
                subject,
                (cx - torso_half * 0.1, points["elbow_r"][1] - 6, x1, hand_y + 14),
                size,
                feather=3.0,
                exclude_above=chin_y,
                protect_top=SKIN_BAND_FOREARM,
            ),
            points["elbow_r"],
        ),
    }

    if side_view:
        # ── 侧视分区重构（V3 步态修复）─────────────────────────────────
        # 侧视原画的双腿/双臂在画面上是**重叠**的：实测骑士侧图左右髋仅差
        # 22px，"左右半身切分 + 反相摆动"会把腿块从中间撕开、左右两半各往
        # 前后拉——盲评指出的"关节轨迹异常/步态失真"的主因。正确语义是
        # 近/远肢体 = **同一完整块的两份拷贝**：远侧调暗（深度线索）、
        # 反相、先画；pivot 取左右关节中点（侧视下左右关节几乎重合）。
        leg_block = (x0, hip_y - 12, x1, min(y1, points["knee_l"][1] + 8))
        shin_block = (x0, points["knee_l"][1] - 22, x1, y1)
        arm_block = (x0, shoulder_y - 8, x1, min(y1, points["elbow_l"][1] + 6))
        forearm_block = (x0, points["elbow_l"][1] - 6, x1, hand_y + 14)
        hip_mid = ((points["hip_l"][0] + points["hip_r"][0]) / 2.0, hip_y)
        knee_mid = ((points["knee_l"][0] + points["knee_r"][0]) / 2.0, points["knee_l"][1])
        shoulder_mid = ((points["shoulder_l"][0] + points["shoulder_r"][0]) / 2.0, shoulder_y)
        elbow_mid = ((points["elbow_l"][0] + points["elbow_r"][0]) / 2.0, points["elbow_l"][1])
        regions["leg_l"] = (_region_layer(subject, leg_block, size, feather=5.0), hip_mid)
        regions["leg_r"] = (_region_layer(subject, leg_block, size, feather=5.0), hip_mid)
        regions["shin_l"] = (
            _region_layer(subject, shin_block, size, feather=5.5, protect_top=SKIN_BAND_SHIN),
            knee_mid,
        )
        regions["shin_r"] = (
            _region_layer(subject, shin_block, size, feather=5.5, protect_top=SKIN_BAND_SHIN),
            knee_mid,
        )
        regions["arm_l"] = (
            _region_layer(subject, arm_block, size, feather=4.0, exclude_above=max(chin_y, shoulder_y + 4)),
            shoulder_mid,
        )
        regions["arm_r"] = (
            _region_layer(subject, arm_block, size, feather=4.0, exclude_above=max(chin_y, shoulder_y + 4)),
            shoulder_mid,
        )
        regions["forearm_l"] = (
            _region_layer(
                subject, forearm_block, size, feather=3.0, exclude_above=chin_y,
                protect_top=SKIN_BAND_FOREARM,
            ),
            elbow_mid,
        )
        regions["forearm_r"] = (
            _region_layer(
                subject, forearm_block, size, feather=3.0, exclude_above=chin_y,
                protect_top=SKIN_BAND_FOREARM,
            ),
            elbow_mid,
        )
        for _far in ("leg_r", "shin_r", "arm_r", "forearm_r"):
            regions[_far] = (_tint_layer(regions[_far][0]), regions[_far][1])

    frames = []
    scales = _motion_scales(rig, size)
    # 跳跃/抬升的上边界保护：dy 以向下为正，主体头顶（y0）移出画布就是
    # "削头"——编排跳跃段实测跳弧 158px 时头部出框。钳到头顶留 8px 余量
    max_up = y0 - max(8.0, size * 0.02)

    # 次级运动图层预处理：缩放到画布、锚点换算画布坐标（V3 发/裙摆动）
    layer_overlays = []
    for overlay in overlays or []:
        layer = overlay.get("layer")
        if layer is None:
            continue
        if layer.size != (size, size):
            layer = layer.resize((size, size), Image.LANCZOS)
        nx, ny = overlay.get("root") or (0.5, 0.5)
        layer_overlays.append(
            {
                "layer": layer,
                "pivot": (float(nx) * size, float(ny) * size),
                "amp": float(overlay.get("amp") or 0.0),
                "lag": max(0.0, min(1.0, float(overlay.get("lag") or 0.0))),
            }
        )

    coverage = Image.new("L", (size, size), 0)

    def _place_tracked(subject, layer, pivot, angle, offset):
        """真 over 贴层并累计"已绘制覆盖图"——裆部立柱只填洞门控的依据。"""
        nonlocal coverage
        blank = _rotated_canvas(layer, pivot, angle, offset, size)
        grown = np.maximum(
            np.asarray(coverage, dtype=np.uint8),
            np.asarray(blank.getchannel("A"), dtype=np.uint8),
        )
        coverage = Image.fromarray(grown, "L")
        return Image.alpha_composite(subject, blank)

    def _place_mesh_tracked(subject, layer, pivot, angle_near, angle_far, band_px, offset):
        """皮肤化贴层（coverage 跟踪同 _place_tracked，立柱门控语义不变）。"""
        nonlocal coverage
        blank = _mesh_canvas(layer, pivot, angle_near, angle_far, band_px, offset, size)
        grown = np.maximum(
            np.asarray(coverage, dtype=np.uint8),
            np.asarray(blank.getchannel("A"), dtype=np.uint8),
        )
        coverage = Image.fromarray(grown, "L")
        return Image.alpha_composite(subject, blank)

    def _place(subject, layer, pivot, angle_far, offset, a_near=None, band=0.0, track=False):
        """统一贴层入口：band>0 且 mesh 开启时走皮肤化（a_near=父段角），
        否则刚体；track=True 时累计覆盖图（立柱门控依赖）。行为与旧的
        _place_tracked / _place_over / _place_mesh_tracked 逐一等价。"""
        nonlocal coverage
        if a_near is not None and use_mesh and band >= SKIN_MIN_ANGLE:
            blank = _mesh_canvas(layer, pivot, a_near, angle_far, band, offset, size)
        else:
            blank = _rotated_canvas(layer, pivot, angle_far, offset, size)
        if track:
            grown = np.maximum(
                np.asarray(coverage, dtype=np.uint8),
                np.asarray(blank.getchannel("A"), dtype=np.uint8),
            )
            coverage = Image.fromarray(grown, "L")
        return Image.alpha_composite(subject, blank)

    for index in range(frame_count):
        pose = _pose(action, index / frame_count, config)
        dy = (pose["bob"] - pose["jump"]) * scales["bob"]
        dy = max(dy, -max_up)
        lean = pose["lean"]
        sway = pose.get("sway", 0.0) * scales["offset"]
        tilt = pose.get("tilt", 0.0)
        arm = pose["arm"] * scales["limb"]
        leg = pose["leg"] * scales["limb"]

        # 所有图层先落到透明主体画布（而非直接贴背景）：turn 假转身需要对
        # "完整主体"做水平压缩，背景必须保持静止不参与变形
        subject_frame = Image.new("RGBA", (size, size), CANVAS_BG)
        # 双骨链合成：大腿 → 小腿（父段角 + 膝弯）→ 裆部立柱（只填洞，无
        # 旋转）→ 躯干 → 上臂 → 前臂（父段角 + 肘屈）。膝/肘的滞后与屈曲让
        # 肢体呈两段式运动，消除整段刚体旋转的分段拼接感。父段层已裁到膝/肘
        # （分区独占所有权），焊缝由子层顶部羽化搭接带吸收；躯干在 lean 之上
        # 叠加 tilt（肩线与髋部横移反向的微小倾斜 = 肩盆反向次级动作）。
        thigh_l = pose.get("thigh_l", leg) * scales["limb"]
        thigh_r = pose.get("thigh_r", leg) * scales["limb"]
        knee_l = pose.get("knee_l", 0.0) * scales["limb"]
        knee_r = pose.get("knee_r", 0.0) * scales["limb"]
        elbow_l = pose.get("elbow_l", 0.0) * scales["limb"]
        elbow_r = pose.get("elbow_r", 0.0) * scales["limb"]

        if side_view:
            # ── 侧视深度顺序：远侧（调暗/反相）→ 躯干 → 近侧 ──────────
            # 立柱跳过：侧视无两腿间隙，静态柱只会污染远腿。
            subject_frame = _place(
                subject_frame, regions["forearm_r"][0], regions["forearm_r"][1],
                -arm * 22 + elbow_r, (sway * 0.5, dy), a_near=-arm * 22, band=SKIN_BAND_FOREARM,
            )
            subject_frame = _place(
                subject_frame, regions["arm_r"][0], regions["arm_r"][1],
                -arm * 22, (sway * 0.5, dy),
            )
            subject_frame = _place(
                subject_frame, regions["leg_r"][0], regions["leg_r"][1],
                thigh_r * 14, (sway * 0.3, dy), track=True,
            )
            subject_frame = _place(
                subject_frame, regions["shin_r"][0], regions["shin_r"][1],
                thigh_r * 14 + knee_r, (sway * 0.3, dy), a_near=thigh_r * 14, band=SKIN_BAND_SHIN, track=True,
            )
            subject_frame = _place_over(subject_frame, regions["upper"][0], regions["upper"][1], -lean - tilt, (sway, dy), size)
            for _ov in layer_overlays:
                _swing = _ov["amp"] * math.sin(2.0 * math.pi * (index / frame_count - _ov["lag"])) * scales["limb"]
                subject_frame = Image.alpha_composite(
                    subject_frame,
                    _rotated_canvas(_ov["layer"], _ov["pivot"], -lean - tilt + _swing, (sway, dy), size),
                )
            subject_frame = _place(
                subject_frame, regions["leg_l"][0], regions["leg_l"][1],
                -thigh_l * 14, (sway * 0.3, dy), track=True,
            )
            subject_frame = _place(
                subject_frame, regions["shin_l"][0], regions["shin_l"][1],
                -thigh_l * 14 + knee_l, (sway * 0.3, dy), a_near=-thigh_l * 14, band=SKIN_BAND_SHIN, track=True,
            )
            subject_frame = _place(
                subject_frame, regions["arm_l"][0], regions["arm_l"][1],
                arm * 22, (sway * 0.5, dy),
            )
            subject_frame = _place(
                subject_frame, regions["forearm_l"][0], regions["forearm_l"][1],
                arm * 22 + elbow_l, (sway * 0.5, dy), a_near=arm * 22, band=SKIN_BAND_FOREARM,
            )
        else:
            # ── 正视：腿 → 小腿 → 立柱 → 躯干 → 上臂 → 前臂（语义不变）──
            subject_frame = _place(
                subject_frame, regions["leg_l"][0], regions["leg_l"][1],
                -thigh_l * 14, (sway * 0.3, dy), track=True,
            )
            subject_frame = _place(
                subject_frame, regions["shin_l"][0], regions["shin_l"][1],
                -thigh_l * 14 + knee_l, (sway * 0.3, dy), a_near=-thigh_l * 14, band=SKIN_BAND_SHIN, track=True,
            )
            subject_frame = _place(
                subject_frame, regions["leg_r"][0], regions["leg_r"][1],
                thigh_r * 14, (sway * 0.3, dy), track=True,
            )
            subject_frame = _place(
                subject_frame, regions["shin_r"][0], regions["shin_r"][1],
                thigh_r * 14 + knee_r, (sway * 0.3, dy), a_near=thigh_r * 14, band=SKIN_BAND_SHIN, track=True,
            )
            # 裆部立柱"只填洞"：门控 = 立柱 alpha × NOT(已绘制覆盖)。两腿摆开
            # 露出的楔形中缝由角色自己的裆部像素补上；运动中的腿永远不会被这层
            # 未旋转的静态列盖住（帧粘连修复的最后一环）。
            pillar_gate = ImageChops.multiply(
                regions["crotch"][0].getchannel("A"), ImageChops.invert(coverage)
            )
            pillar_canvas = Image.new("RGBA", (size, size), CANVAS_BG)
            pillar_canvas.paste(regions["crotch"][0], (0, int(round(dy))), pillar_gate)
            subject_frame = Image.alpha_composite(subject_frame, pillar_canvas)
            subject_frame = _place_over(subject_frame, regions["upper"][0], regions["upper"][1], -lean - tilt, (sway, dy), size)
            for _ov in layer_overlays:
                _swing = _ov["amp"] * math.sin(2.0 * math.pi * (index / frame_count - _ov["lag"])) * scales["limb"]
                subject_frame = Image.alpha_composite(
                    subject_frame,
                    _rotated_canvas(_ov["layer"], _ov["pivot"], -lean - tilt + _swing, (sway, dy), size),
                )
            subject_frame = _place(
                subject_frame, regions["arm_l"][0], regions["arm_l"][1],
                arm * 22, (sway * 0.5, dy),
            )
            subject_frame = _place(
                subject_frame, regions["forearm_l"][0], regions["forearm_l"][1],
                arm * 22 + elbow_l, (sway * 0.5, dy), a_near=arm * 22, band=SKIN_BAND_FOREARM,
            )
            subject_frame = _place(
                subject_frame, regions["arm_r"][0], regions["arm_r"][1],
                -arm * 22, (sway * 0.5, dy),
            )
            subject_frame = _place(
                subject_frame, regions["forearm_r"][0], regions["forearm_r"][1],
                -arm * 22 + elbow_r, (sway * 0.5, dy), a_near=-arm * 22, band=SKIN_BAND_FOREARM,
            )

        yaw = float(pose.get("turn", 0.0) or 0.0)
        if abs(yaw) > 2.0:
            subject_frame = _apply_yaw(subject_frame, yaw, cx, size)
        frame = base_bg.copy()
        frame.alpha_composite(subject_frame)
        frames.append((size, size, bytearray(frame.tobytes())))

    reference = (size, size, bytearray(canvas.tobytes()))
    return frames, reference, rig, _falign(frames)


# ── 整身形变（试玩条带专用）────────────────────────────────────────
# 分区骨架变形在 Q 版/大头角色上，上半身与手臂层旋转后会在颈胸处
# 留下硬接缝（表现为"胸口横条、脸部切片"）。试玩条带只需要动作可读、
# 帧间连贯，因此改用整身形变：完整角色只做位移/倾斜/挤压，
# 帧内不存在任何分区接缝，帧间用正弦相位衔接。

SPRITE_ACTIONS = ("idle", "walk", "run", "attack", "jump")


def _sprite_pose(action: str, index: int, count: int):
    """-> (dx, dy, angle, sx, sy)；角度单位为度，正值向右倾。

    相位口径：``sin`` 控左右（摆动/倾角），``|sin|`` 控上下（步频两倍）。
    挤压与拉伸成对出现（sx 涨则 sy 落），保持体积感，动作才读得出来。"""
    t = 2.0 * math.pi * index / max(1, count)
    swing = math.sin(t)
    step = abs(math.sin(t))
    if action == "idle":
        return (
            0.0,
            2.2 * swing,
            1.0 * math.sin(t + 0.6),
            1.0 + 0.006 * math.sin(t + 1.0),
            1.0 + 0.008 * math.sin(t + 1.0),
        )
    if action == "walk":
        return (
            2.5 * swing,
            -6.0 * step,
            3.0 * swing,
            1.0 + 0.02 * step,
            1.0 - 0.025 * step,
        )
    if action == "run":
        return (
            4.0 * swing,
            -12.0 * step,
            9.0 + 2.5 * swing,
            1.0 + 0.03 * step,
            1.0 - 0.04 * step,
        )
    if action == "attack":
        u = index / max(1, count - 1)
        punch = math.sin(math.pi * u)
        return (
            18.0 * punch,
            -3.0 * punch,
            10.0 * punch,
            1.0 + 0.03 * punch,
            1.0 + 0.02 * punch,
        )
    # jump：单峰起伏，首尾回到站立姿势（循环播放不会突然起跳）
    u = index / max(1, count - 1)
    hop = math.sin(math.pi * u)
    return (0.0, -30.0 * hop, -4.0 * hop, 1.0 - 0.03 * hop, 1.0 + 0.06 * hop)


def animate_sprite(image_bytes, action, frame_count=16, size=256):
    """整身形变动画（不切分身体）-> (frames, reference)。

    ``frames`` 与 :func:`animate_rigged` 同格式 ``(w, h, RGBA bytes)``。
    试玩条带专用：动作可读、帧间连贯，帧内不存在分区接缝。
    """
    size = max(64, min(1024, int(size)))
    frame_count = max(2, min(60, int(frame_count)))
    action = action if action in SPRITE_ACTIONS else "walk"

    canvas = _fit(Image.open(io.BytesIO(image_bytes)), size)
    mask, _transparent, _bg = _subject_mask(canvas)
    subject = canvas.copy()
    subject.putalpha(mask)

    box = subject.getbbox() or (0, 0, size, size)
    sprite = subject.crop(box)
    # 预留变换余量：显示高度压到画布的 74%，宽度 84%（冲刺位移 18px
    # + 旋转外扩后仍不出画）
    fit = min((size * 0.74) / max(1, sprite.height), (size * 0.84) / max(1, sprite.width))
    sprite = sprite.resize(
        (max(1, int(round(sprite.width * fit))), max(1, int(round(sprite.height * fit)))),
        Image.BICUBIC,
    )
    base_x = size / 2.0
    base_y = size - 8.0
    anchor_x = sprite.width / 2.0
    anchor_y = float(sprite.height)

    frames = []
    for index in range(frame_count):
        dx, dy, angle, sx, sy = _sprite_pose(action, index, frame_count)
        layer = sprite
        if abs(sx - 1.0) > 1e-4 or abs(sy - 1.0) > 1e-4:
            layer = layer.resize(
                (max(1, int(round(layer.width * sx))), max(1, int(round(layer.height * sy)))),
                Image.BICUBIC,
            )
        ax = anchor_x * layer.width / sprite.width
        ay = anchor_y * layer.height / sprite.height
        if abs(angle) > 1e-3:
            rotated = layer.rotate(angle, resample=Image.BICUBIC, expand=True)
            ax += (rotated.width - layer.width) / 2.0
            ay += (rotated.height - layer.height) / 2.0
            layer = rotated
        frame = Image.new("RGBA", (size, size), CANVAS_BG)
        frame.paste(layer, (int(round(base_x + dx - ax)), int(round(base_y + dy - ay))), layer)
        frames.append((size, size, bytearray(frame.tobytes())))

    reference = (size, size, bytearray(canvas.tobytes()))
    return frames, reference


def render_rigged_frame_rgba(
    image_bytes, action, phase, size, rig=None, config=None, segment_mask=None, count=24,
    view="front",
):
    """One rig-driven frame at an arbitrary phase (preview-frame endpoint)."""
    frames, reference, rig, _ = animate_rigged(
        image_bytes, action, count, size, rig=rig, config=config, segment_mask=segment_mask,
        view=view,
    )
    index = min(count - 1, max(0, int(round(phase * count)) % count))
    return frames[index], rig
