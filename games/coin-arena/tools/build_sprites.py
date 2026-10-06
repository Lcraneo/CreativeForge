"""游戏精灵图集构建 v2：逐帧边界洪泛抠像，产出透明底 sprite sheet。

v1（静态掩膜投射，git 5691f44）的教训：把白底源图的主体掩膜按同一
裁剪框投射到全部 32 帧——i2v 大动作帧（attack 转体甩鼓、walk 腿部
摆动）肢体大量越出静态掩膜，掩膜内收空处露出视频白底，成片出现大块
白色幽灵剪影（用户报告的"动画序列空白区域"根因）。静态掩膜对大动作
动画是根本性失效，调参无解。

v2 逐帧抠像，两通道：

1. 主角：i2v 帧本身白底（白底化源图驱动的 i2v，构图子句锁摄像机），
   每帧 _flood_subject 边界洪泛 + 封闭洞吸收 → 肢体摆到哪抠到哪；
2. 敌人：角色包 sheet 底是「黑色分隔条 + 灰紫渐变 + 白色地光」，黑色
   硬边跨不过洪泛阈值——水平裁掉黑条后洪泛（种子直接落在渐变带上，
   逐像素平滑可走通全程），残留的白色地光细丝用采样背景色集的封闭洞
   吸收二次清理；

共性护栏与边缘质量：

- 面积护栏：某帧主体面积 < 全片中位面积 35% 视为洪泛漏进主体（米白
  上衣被吃），回退用邻帧掩膜并告警——不再依赖 AI 源图掩膜做先验；
- 1px 腐蚀 + 羽化：切掉与底色混合的抗锯齿边（视频压缩渗白），角色
  深色轮廓不吃进，深色游戏底上无白晕；
- 幽灵帧重定时：i2v 自带的白色运动拖影/循环混合伪影（attack 挥棒楔
  形白块、各动作 30/31 帧白雾——源帧信息已毁，抠不掉）按目检清单 +
  内部近白占比指标（GHOST_A）检出，重定时到最近干净帧。

用法：python games/coin-arena/tools/build_sprites.py
输入：studio/backend/data/_arena_hero_white_frames.json（主角白底 i2v
帧 URL 表，需 8600 后端在跑）+ exports/ 下 ast38382 最新角色包 zip。
"""

import httpx
import io
import json
import numpy as np
import os
import sys
import zipfile

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

BASE = "http://127.0.0.1:8600"
OUT = os.path.join(HERE, os.pardir, "assets")
EXPORTS = os.path.join(REPO, "studio", "backend", "exports")
DEBUG_DIR = os.path.join(REPO, "studio", "backend", "data", "_arena_dbg")
FRAME_H = 192
ENEMY_BLACK_BAR = 30   # 角色包 sheet 帧左右黑色分隔条宽度
AREA_GUARD = 0.35      # 帧主体面积/中位面积 低于此值 → 洪泛漏进主体
GHOST_A = 0.13         # 内部不透明近白占比阈值（i2v 白色运动拖影检出）

# 目检定案的幽灵帧（源：i2v 白色运动模糊 / 循环混合伪影，信息已毁不可
# 抠）→ 用最近干净帧重定时。新素材重跑后以 GHOST_A 自动检出兜底。
GHOST_FRAMES = {
    "hero_idle": {30: 29, 31: 29},
    "hero_walk": {23: 22, 30: 29, 31: 29},
    "hero_run": {1: 0, 18: 17, 30: 29, 31: 29},
    "hero_attack": {2: 1, 4: 3, 5: 3, 11: 10, 27: 26, 30: 29, 31: 29},
}

c = httpx.Client(timeout=120)


def _border_bg(rgb):
    from artgen.sourceanim import _border_bg

    return _border_bg(rgb)


def flood_matte(rgb, absorb_refs):
    """边界洪泛 + 封闭洞吸收（逐参考色）→ L 掩膜。"""
    from artgen.riganim import _absorb_enclosed_background
    from artgen.sourceanim import _flood_subject

    mask = _flood_subject(rgb)
    for ref in absorb_refs:
        mask = _absorb_enclosed_background(mask, rgb, bg_color=ref)
    return mask


def refine_mask(mask):
    """1px 腐蚀切掉渗白抗锯齿边，再羽化——深色底上无白晕。"""
    return mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.0))


def composite(rgb, mask):
    rgba = rgb.convert("RGBA")
    arr = np.asarray(rgba).copy()
    arr[:, :, 3] = np.asarray(mask)
    return Image.fromarray(arr, "RGBA")


def matte_hero_frame(rgb):
    """主角白底 i2v 帧：边界洪泛，封闭洞参考 = 边缘中值色（近白）。→ L 掩膜"""
    return refine_mask(flood_matte(rgb, [_border_bg(rgb)]))


def matte_enemy_frame(rgb):
    """敌人包帧：裁黑条 → 洪泛走渐变 → 采样背景色集吸收白光细丝。→ L 掩膜"""
    w, h = rgb.size
    inner = rgb.crop((ENEMY_BLACK_BAR, 0, w - ENEMY_BLACK_BAR, h))
    # 背景参考色：内框左列自上而下采样（覆盖灰紫渐变全程 + 白色地光）
    ip = inner.load()
    iw, ih = inner.size
    refs = list({ip[2, y] for y in range(2, ih - 2, max(8, ih // 24))})
    mask = flood_matte(inner, refs + [(255, 255, 255)])
    full = Image.new("L", (w, h), 0)
    full.paste(refine_mask(mask), (ENEMY_BLACK_BAR, 0))
    return full


class AreaGuard:
    """洪泛漏进主体的护栏：面积骤降 → 回退邻帧掩膜。"""

    def __init__(self):
        self.areas = []
        self.prev_mask = None

    def check(self, mask):
        hist = mask.histogram()
        area = sum(hist[128:])  # 半透明以上视为主体
        self.areas.append(area)
        solid = sorted(self.areas)[len(self.areas) // 2] if self.areas else 0
        if self.prev_mask is not None and solid and area < solid * AREA_GUARD:
            print(f"  ⚠ 面积护栏触发（{area} < {solid * AREA_GUARD:.0f}），回退邻帧掩膜")
            return self.prev_mask
        self.prev_mask = mask
        return mask


def matte_sequence(frames_rgb, matting):
    """逐帧取掩膜 + 面积护栏，护栏通过后统一合成。"""
    guard = AreaGuard()
    out = []
    for rgb in frames_rgb:
        mask = guard.check(matting(rgb))
        out.append(composite(rgb, mask))
    return out


def ghost_score(frame_rgba):
    """内部（掩膜腐蚀 5px）不透明近白占比——i2v 白色运动拖影的指纹。

    半透明雾测不准（i2v 软渲染普遍半透明），只测实心白块。"""
    arr = np.asarray(frame_rgba).astype(np.int16)
    a = arr[:, :, 3]
    if (a > 32).sum() < 50:
        return 0.0
    interior = (
        np.asarray(Image.fromarray(((a > 32) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(11))) > 128
    )
    if interior.sum() < 30:
        return 0.0
    rgb = arr[:, :, :3]
    whiteish = (rgb.min(axis=2) > 200) & ((rgb.max(axis=2) - rgb.min(axis=2)) < 26)
    return float((interior & whiteish).sum()) / float(interior.sum())


def replace_ghost_frames(frames_rgba, name):
    """坏帧重定时：显式清单优先，GHOST_A 检出兜底（取最近的前一干净帧）。"""
    repl = dict(GHOST_FRAMES.get(name) or {})
    for i, frame in enumerate(frames_rgba):
        if i in repl or ghost_score(frame) <= GHOST_A:
            continue
        repl[i] = i - 1 if i > 0 else 1
        print(f"  ⚠ {name} f{i} 指标 {ghost_score(frame):.2f} 超阈值，重定时")
    for dst, src in sorted(repl.items()):
        while src in repl:  # 源帧本身也是坏帧 → 顺链到干净帧
            src = repl[src]
        frames_rgba[dst] = frames_rgba[src]
    if repl:
        print(f"  幽灵帧重定时 {name}: {sorted(repl)}")


def build_sheet(name, frames_rgba, debug=False):
    # 全帧联合透明 bbox 裁掉死区，缩放到统一帧高
    bbox = frames_rgba[0].getbbox()
    for f in frames_rgba[1:]:
        b = f.getbbox()
        if b:
            bbox = (min(bbox[0], b[0]), min(bbox[1], b[1]), max(bbox[2], b[2]), max(bbox[3], b[3]))
    cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tw = max(48, round(FRAME_H * cw / ch))
    sheet = Image.new("RGBA", (tw * len(frames_rgba), FRAME_H), (0, 0, 0, 0))
    for i, f in enumerate(frames_rgba):
        sheet.paste(f.crop(bbox).resize((tw, FRAME_H), Image.LANCZOS), (i * tw, 0))
    sheet.save(os.path.join(OUT, f"{name}.png"), "PNG", optimize=True)

    fw = sheet.width // len(frames_rgba)
    if debug:
        dark = (36, 32, 44, 255)
        rows = 4
        per = (len(frames_rgba) + rows - 1) // rows
        board = Image.new("RGBA", (fw * per, FRAME_H * rows), dark)
        for i, f in enumerate(frames_rgba):
            board.alpha_composite(
                f.crop(bbox).resize((tw, FRAME_H), Image.LANCZOS), ((i % per) * tw, (i // per) * FRAME_H)
            )
        board.convert("RGB").save(os.path.join(DEBUG_DIR, f"v2_{name}.png"))
    print(f"{name}: {len(frames_rgba)}帧 帧宽{fw}")
    return {"file": f"{name}.png", "frames": len(frames_rgba), "fps": 12, "fw": fw, "fh": FRAME_H}


def fetch_image(url):
    data = httpx.get(url, timeout=60).content if str(url).startswith("http") else c.get(
        BASE + url, timeout=60
    ).content
    return Image.open(io.BytesIO(data)).convert("RGB")


def build_hero(frames_table):
    result = {}
    for action, urls in frames_table.items():
        frames = [fetch_image(u) for u in urls]
        matted = matte_sequence(frames, matte_hero_frame)
        replace_ghost_frames(matted, f"hero_{action}")
        result[f"hero_{action}"] = build_sheet(f"hero_{action}", matted, debug=True)
    return result


def build_enemy():
    result = {}
    pkg = max(
        (os.path.join(EXPORTS, f) for f in os.listdir(EXPORTS) if f.startswith("ast38382") and f.endswith(".zip")),
        key=os.path.getmtime,
    )
    with zipfile.ZipFile(pkg) as z:
        m = json.loads(z.read("manifest.json"))
        for entry in m.get("animations") or []:
            action = entry.get("action")
            if action not in ("idle", "walk"):
                continue
            raw = Image.open(
                io.BytesIO(z.read("animations/{}__{}_sheet.png".format(action, entry["engine"])))
            ).convert("RGB")
            n = int(entry.get("frames") or 1)
            fw = raw.width // n
            frames = [raw.crop((i * fw, 0, (i + 1) * fw, raw.height)) for i in range(n)]
            result[f"enemy_{action}"] = build_sheet(
                f"enemy_{action}", matte_sequence(frames, matte_enemy_frame), debug=True
            )
    return result


def main():
    os.makedirs(DEBUG_DIR, exist_ok=True)
    manifest = json.load(open(os.path.join(OUT, "manifest.json")))
    hero_frames = json.load(open(os.path.join(REPO, "studio", "backend", "data", "_arena_hero_white_frames.json")))
    manifest.update(build_hero(hero_frames))
    manifest.update(build_enemy())
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=2)
    print("完成")


if __name__ == "__main__":
    main()
