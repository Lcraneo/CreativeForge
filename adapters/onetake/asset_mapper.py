"""asset_mapper — CreativeAsset → 展示素材清单 + 合成工作目录素材准备。

素材解析失败抛 MissingMaterialError（宁可报错不给模板：缺原画/缺动作帧的
资产不做静默兜底，前端按 409 + 中文可读提示引导先去生成）。
"""

import os
import re

from PIL import Image

DEFAULT_PIXEL_GRID = 24
FRAME_SIZE = 288          # 合成内帧展示边长（与 i2v 条带压缩上限一致）
ART_SIZE = 1024
PREFERRED_ACTIONS = ("attack", "walk", "run", "idle", "jump")


class MissingMaterialError(RuntimeError):
    """展示所需的必需素材缺失（无原画 / 无动作帧）。"""


def _resolve_art(asset) -> bytes:
    """真实原画字节（与 /api/assets/{id}/image.png 的真实优先语义同源）。"""

    from studio.backend.animation_service.service import AnimationService

    art = AnimationService(".")._asset_render(asset)
    if not art:
        raise MissingMaterialError("该资产没有可用的真实原画（先在创作工作台生成角色原画）")
    return art


def _resolve_frames(asset, animation_dir) -> list[bytes]:
    """该资产最新的动作帧序列（优先 attack）。读动画 meta 的逐帧产物。"""

    import glob as _glob
    import json as _json

    best = None
    for meta_path in _glob.glob(os.path.join(animation_dir, "*.json")):
        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = _json.load(handle)
        except (ValueError, OSError):
            continue
        if meta.get("asset_id") != (asset or {}).get("id"):
            continue
        urls = meta.get("frame_urls") or []
        if len(urls) < 4:
            continue
        action = meta.get("requested_action") or meta.get("action") or ""
        rank = PREFERRED_ACTIONS.index(action) if action in PREFERRED_ACTIONS else len(PREFERRED_ACTIONS)
        stamp = meta.get("created_at", 0)
        if best is None or rank < best[0] or (rank == best[0] and stamp > best[1]):
            best = (rank, stamp, urls)

    if best is None:
        raise MissingMaterialError("该资产还没有动作帧（先在试玩区/动画工作台生成动作，再来生成发布片）")

    frames = []
    for url in best[2]:
        name = os.path.basename(url.split("?")[0])
        path = os.path.join(animation_dir, name)
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                frames.append(handle.read())
    if len(frames) < 4:
        raise MissingMaterialError("动作帧文件缺失（历史记录不完整），请重新生成动作")
    return frames


def _load_image(data):
    from io import BytesIO

    from PIL import Image

    return Image.open(BytesIO(data)).convert("RGBA")


def _fit_square(image, size):
    """contain-fit 到透明方形画布（合成内的帧/原画统一画幅）。"""

    if image.mode != "RGBA":
        image = image.convert("RGBA")
    scale = min(size / max(1, image.width), size / max(1, image.height))
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(resized, ((size - resized.width) // 2, (size - resized.height) // 2), resized)
    return canvas


def _pixel_rebuild(image, grid=DEFAULT_PIXEL_GRID):
    """PReCon 观感示意：网格降采样 + 最近邻放大（展示层的确定性重建，
    真实 PReCon 管线见 precon/，这里只取其视觉语义）。"""

    flat = _fit_square(image.convert("RGB"), 1024)
    small = flat.resize((grid, grid), Image.BOX)
    return small.resize((1024, 1024), Image.NEAREST)


def prepare_job_assets(job_dir, asset, animation_dir, third_party_dir) -> dict:
    """建合成工作目录并准备全部素材。返回注入 comp 的 CF.assets 片段与 meta。"""

    art_bytes = _resolve_art(asset)
    frame_bytes = _resolve_frames(asset, animation_dir)

    assets_dir = os.path.join(job_dir, "assets")
    fonts_dir = os.path.join(assets_dir, "fonts")
    os.makedirs(assets_dir, exist_ok=True)
    os.makedirs(fonts_dir, exist_ok=True)

    art = _load_image(art_bytes)
    _fit_square(art, ART_SIZE).save(os.path.join(assets_dir, "art.png"))
    _pixel_rebuild(art).save(os.path.join(assets_dir, "pixel.png"))

    act_names = []
    for index, data in enumerate(frame_bytes):
        name = "act_{:02d}.png".format(index)
        _fit_square(_load_image(data), FRAME_SIZE).save(os.path.join(assets_dir, name))
        act_names.append("assets/" + name)
    # 引擎预览窗复用同一动作序列（运行中观感）；帧取样隔帧抽取更接近低帧率引擎
    eng_names = [act_names[i] for i in range(0, len(act_names), max(1, len(act_names) // 12))]

    for src_rel, dst_rel in (("lib/motion.js", "motion.js"), ("lib/ui_kit.js", "ui_kit.js")):
        src = os.path.join(third_party_dir, src_rel)
        if os.path.isfile(src):
            with open(src, "rb") as handle:
                payload = handle.read()
            with open(os.path.join(job_dir, dst_rel), "wb") as dst:
                dst.write(payload)
    for face in ("Inter.ttf", "InstrumentSerif.ttf", "GeistMono.ttf"):
        src = os.path.join(third_party_dir, "looks", "fonts", face)
        if os.path.isfile(src):
            with open(src, "rb") as handle:
                payload = handle.read()
            with open(os.path.join(fonts_dir, face), "wb") as dst:
                dst.write(payload)

    return {
        "art": "assets/art.png",
        "pixel": "assets/pixel.png",
        "act": act_names,
        "engine": eng_names,
        "act_fps": 10,
        "engine_fps": 12,
    }


def slugify(text, fallback="asset"):
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(text or "").strip()).strip("-")
    return (slug or fallback)[:32]
