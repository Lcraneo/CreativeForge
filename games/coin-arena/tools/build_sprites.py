"""游戏精灵图集构建：AI 分割掩膜 + 帧对齐投射，产出透明底 sprite sheet。

为什么不用逐帧色键：主角米白上衣/敌人银发与背景同色系，任何颜色泛洪
都会吃进主体（实测）。正确姿势与项目 _stabilize_background 同源——

1. 每个资产只做一次 AI 白底化（ImageEditProvider + SEGMENT_PROMPT，
   qwen-image-edit 把角色抠到纯白底），_flood_subject 得到高精度主体
   掩膜 M；
2. i2v 摄像机锁定（构图子句保证），帧 = 源图主体 bbox（外扩 6% + 补
   方形）区域的动画——把 M 按同一裁剪框投射到每帧，膨胀 8px 吸收肢体
   摆动余量，羽化 2px；
3. 白底连接清理：与帧边界连通的近白区（膨胀掩膜之外）置透明，清除
   膨胀环内的残余背景；主体内部浅色被掩膜保护，不受影响。

用法：python games/coin-arena/tools/build_sprites.py
输入：studio/backend/data/_arena_hero_white_frames.json（主角白底 i2v 帧
URL 表）+ 敌人角色包 zip（exports/ 下 ast38382 最新包）。
"""

import base64
import httpx
import io
import json
import os
import sys
import zipfile
from collections import deque

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

BASE = "http://127.0.0.1:8600"
OUT = os.path.join(HERE, os.pardir, "assets")
EXPORTS = os.path.join(REPO, "studio", "backend", "exports")
DEBUG_DIR = os.path.join(REPO, "studio", "backend", "data")
FRAME_H = 192
MARGIN = 0.06   # 与 _crop_to_subject 同款外扩
DILATE = 8      # 肢体摆动余量

c = httpx.Client(timeout=120)


def white_flood_mask(white_img):
    """纯白底 → 主体掩膜：洪泛 + 封闭白洞吸收（臂弯/腿间的封闭背景洞）。"""
    from artgen.riganim import _absorb_enclosed_background
    from artgen.sourceanim import _border_bg, _flood_subject

    rgb = white_img.convert("RGB")
    mask = _flood_subject(rgb)
    mask = _absorb_enclosed_background(mask, rgb, bg_color=_border_bg(rgb))
    return mask


def crop_square_box(mask):
    """主体 bbox 外扩 6% 并补成方形（模拟 _crop_to_subject 的取景）。"""
    bbox = mask.getbbox()
    if not bbox:
        raise RuntimeError("empty mask")
    x0, y0, x1, y1 = bbox
    w, h = mask.size
    pad_x, pad_y = int((x1 - x0) * MARGIN), int((y1 - y0) * MARGIN)
    x0, y0 = max(0, x0 - pad_x), max(0, y0 - pad_y)
    x1, y1 = min(w, x1 + pad_x), min(h, y1 + pad_y)
    side = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    half = side // 2
    return (max(0, cx - half), max(0, cy - half), min(w, cx + half), min(h, cy + half))


def white_connector_cleanup(frame, mask, white_min=216):
    """与帧边界连通的近白背景置透明（膨胀环内的残余背景清理）。

    起点只能在掩膜之外——主体内部的浅色（脸/上衣）被掩膜保护。"""
    px = frame.load()
    mp = mask.load()
    w, h = frame.size
    visited = bytearray(w * h)
    dq = deque()
    border = (
        [(x, 0) for x in range(w)]
        + [(x, h - 1) for x in range(w)]
        + [(0, y) for y in range(h)]
        + [(w - 1, y) for y in range(h)]
    )
    for x, y in border:
        p = px[x, y]
        if mp[x, y] == 0 and min(p[:3]) > white_min:
            visited[y * w + x] = 1
            dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        p = px[x, y]
        px[x, y] = (p[0], p[1], p[2], 0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx]:
                if mp[nx, ny] == 0:
                    q = px[nx, ny]
                    if min(q[:3]) > white_min - 30:
                        visited[ny * w + nx] = 1
                        dq.append((nx, ny))


def apply_mask(frame, mask, dilate=DILATE, hard_cut=False):
    frame = frame.convert("RGBA")
    m = mask.resize(frame.size).filter(ImageFilter.MaxFilter(dilate * 2 + 1))
    m = m.filter(ImageFilter.GaussianBlur(2))
    px, mp = frame.load(), m.load()
    w, h = frame.size
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            px[x, y] = (p[0], p[1], p[2], mp[x, y])
    if hard_cut:
        # 硬裁：紧掩膜（不膨胀）之外一律透明——i2v 白底带暗角时软清理
        # 清不干净，硬裁牺牲少量越界肢体换取零白晕（原地动画可接受）
        tight = mask.resize(frame.size)
        tp = tight.load()
        for y in range(h):
            for x in range(w):
                if tp[x, y] == 0:
                    p = px[x, y]
                    px[x, y] = (p[0], p[1], p[2], 0)
        return frame
    white_connector_cleanup(frame, m)
    return frame


def build_sheet(name, frames_rgb, source_white, debug=False, dilate=DILATE, hard_cut=False):
    """frames_rgb: 原始帧 PIL RGB 列表（同尺寸方形）；source_white: 白底化源图 RGB。"""
    mask_src = white_flood_mask(source_white)
    box = crop_square_box(mask_src)
    mask_crop = mask_src.crop(box)

    frames_out = [apply_mask(frame, mask_crop, dilate=dilate, hard_cut=hard_cut) for frame in frames_rgb]

    # 全帧联合透明 bbox 裁掉死区，缩放到统一帧高
    bbox = frames_out[0].getbbox()
    for f in frames_out[1:]:
        b = f.getbbox()
        if b:
            bbox = (min(bbox[0], b[0]), min(bbox[1], b[1]), max(bbox[2], b[2]), max(bbox[3], b[3]))
    cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tw = max(48, round(FRAME_H * cw / ch))
    sheet = Image.new("RGBA", (tw * len(frames_out), FRAME_H), (0, 0, 0, 0))
    for i, f in enumerate(frames_out):
        sheet.paste(f.crop(bbox).resize((tw, FRAME_H), Image.LANCZOS), (i * tw, 0))
    sheet.save(os.path.join(OUT, f"{name}.png"), "PNG", optimize=True)

    fw = sheet.width // len(frames_out)
    px = sheet.load()
    transparent = sum(
        1 for x in range(0, sheet.width, 8) for y in range(0, sheet.height, 4) if px[x, y][3] == 0
    )
    total = len(range(0, sheet.width, 8)) * len(range(0, sheet.height, 4))
    print(f"{name}: {len(frames_out)}帧 帧宽{fw} 透明占比 {transparent / total:.0%}")

    if debug:
        f0 = sheet.crop((0, 0, fw, FRAME_H))
        magenta = Image.new("RGBA", f0.size, (255, 0, 200, 255))
        magenta.alpha_composite(f0)
        magenta.resize((fw * 2, FRAME_H * 2), Image.NEAREST).convert("RGB").save(
            os.path.join(DEBUG_DIR, f"_dbg4_{name}_f0.png")
        )
    return {"file": f"{name}.png", "frames": len(frames_out), "fps": 12, "fw": fw, "fh": FRAME_H}


def fetch_image(url):
    data = httpx.get(url, timeout=60).content if str(url).startswith("http") else c.get(
        BASE + url, timeout=60
    ).content
    return Image.open(io.BytesIO(data)).convert("RGB")


def png_data_url(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def white_version(rgb_img, editor, cache_key):
    """AI 白底化（带缓存与重试）：qwen-image-edit 输出有随机性，四角不白
    时换种子重试；成功过的白底图落盘复用，保证与当初 i2v 源一致。"""
    cache_path = os.path.join(DEBUG_DIR, "_arena_white_sources.json")
    cache = {}
    if os.path.isfile(cache_path):
        cache = json.load(open(cache_path, encoding="utf-8"))
    if cache.get(cache_key) and os.path.isfile(cache[cache_key]):
        return Image.open(cache[cache_key]).convert("RGB")
    import time as _time

    last_error = None
    for attempt in range(3):
        edit = editor.edit(png_data_url(rgb_img), SEGMENT_PROMPT)
        path = safe_generated_path(edit.get("file"))
        if not path:
            last_error = "无产物"
            continue
        white = Image.open(path).convert("RGB")
        px = white.load()
        w, h = white.size
        corners_ok = all(
            min(px[x, y]) > 225 for x, y in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))
        )
        if corners_ok:
            cache[cache_key] = path
            json.dump(cache, open(cache_path, "w", encoding="utf-8"))
            from PIL import ImageOps

            ImageOps.contain(white, (360, 360)).save(
                os.path.join(DEBUG_DIR, f"_dbg6_white_{cache_key}.png")
            )
            return white
        last_error = f"四角非白（尝试 {attempt + 1}）"
        _time.sleep(1)
    raise RuntimeError(f"AI 白底化失败：{last_error}")


def main():
    from studio.backend.animation_service.service import SEGMENT_PROMPT
    from studio.backend.model_service.service import (
        ModelSettingsStore,
        safe_generated_path,
    )

    globals()["SEGMENT_PROMPT"] = SEGMENT_PROMPT
    globals()["safe_generated_path"] = safe_generated_path
    editor = __import__("studio.backend.model_service.service", fromlist=["ImageEditProvider"]).ImageEditProvider(
        ModelSettingsStore().effective()
    )
    manifest = json.load(open(os.path.join(OUT, "manifest.json")))
    result = {}

    # ── 主角：白底 i2v 帧序列 + 白底化源图 ────────────────────────
    hero_frames = json.load(open(os.path.join(DEBUG_DIR, "_arena_hero_white_frames.json")))
    asset = c.get(f"{BASE}/api/assets/ast43024").json()
    ai_url = (asset.get("source") or {}).get("ai_image", {}).get("url")
    src_bytes = c.get(BASE + ai_url if str(ai_url).startswith("/") else ai_url).content
    hero_white = white_version(
        Image.open(io.BytesIO(src_bytes)).convert("RGB"), editor, cache_key="hero_ast43024"
    )

    for action, urls in hero_frames.items():
        frames = [fetch_image(u) for u in urls]
        result[f"hero_{action}"] = build_sheet(f"hero_{action}", frames, hero_white, debug=True, dilate=6, hard_cut=True)

    # ── 敌人：角色包原始 sheet 拆帧；白底化源 = 敌人正面立绘 ──────
    enemy_pkg = max(
        (os.path.join(EXPORTS, f) for f in os.listdir(EXPORTS) if f.startswith("ast38382") and f.endswith(".zip")),
        key=os.path.getmtime,
    )
    enemy_white = None
    with zipfile.ZipFile(enemy_pkg) as z:
        m = json.loads(z.read("manifest.json"))
        enemy_front = Image.open(io.BytesIO(z.read("artwork/front.png"))).convert("RGB")
    enemy_white = white_version(enemy_front, editor, cache_key="enemy_ast38382")
    with zipfile.ZipFile(enemy_pkg) as z:
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
            result[f"enemy_{action}"] = build_sheet(f"enemy_{action}", frames, enemy_white, debug=True)

    manifest.update(result)
    json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=2)
    print("完成")


if __name__ == "__main__":
    main()
