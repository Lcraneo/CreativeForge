"""游戏精灵图集色键工具：把白底/浅渐变底的横排帧图抠成透明底。

针对 i2v 帧背景的两个现实：①背景不是纯白，有渐变与暗角；②主体轮廓
是抗锯齿硬边。固定容差 + 四角参考色的泛洪会被渐变卡住（实测只清掉
角落附近）。这里用「梯度连续泛洪」：

- 边缘种子：与任一角色参考色接近（<60）的边界像素先行入队，再沿边界
  链式扩散（相邻边界像素色差 <14）——覆盖整条渐变背景带；
- 生长判据：候选与「来源像素」色差 <13（走平滑渐变）或与最近角参考
  色差 <48（跳回大范围底色）——遇到轮廓硬边自然停止；
- 主体内部（被轮廓包围的浅色，如银发高光）与边界不连通，永不误删。

用法：python games/coin-arena/tools/key_frames.py  （就地处理 assets/*.png）
"""

import os
import sys
from collections import deque

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, os.pardir, "assets")
FRAME_W = 192
STEP_TOL = 22  # 在模糊副本上判定——视频帧噪点已消，梯度可走
SEED_TOL = 70
GROW_REF_TOL = 60


def d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def key_frame(img):
    from PIL import ImageFilter

    img = img.convert("RGBA")
    w, h = img.size
    # 掩膜判定用模糊副本（视频帧背景有压缩噪点，逐像素容差走不动渐变）；
    # alpha 回写到原图，保留主体细节
    smooth = img.filter(ImageFilter.GaussianBlur(2))
    px, sp = img.load(), smooth.load()
    corners = [sp[0, 0][:3], sp[w - 1, 0][:3], sp[0, h - 1][:3], sp[w - 1, h - 1][:3]]

    def nearest_corner(p):
        return min(d2(p, c) for c in corners)

    visited = bytearray(w * h)
    dq = deque()
    border = (
        [(x, 0) for x in range(w)]
        + [(x, h - 1) for x in range(w)]
        + [(0, y) for y in range(h)]
        + [(w - 1, y) for y in range(h)]
    )
    for x, y in border:
        if not visited[y * w + x] and nearest_corner(sp[x, y][:3]) < SEED_TOL ** 2:
            visited[y * w + x] = 1
            dq.append((x, y, sp[x, y][:3]))
    for _ in range(3):  # 沿边界链式补种（覆盖渐变带的中段）
        changed = False
        for x, y in border:
            if visited[y * w + x]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (
                    0 <= nx < w
                    and 0 <= ny < h
                    and visited[ny * w + nx]
                    and d2(sp[x, y][:3], sp[nx, ny][:3]) < STEP_TOL ** 2
                ):
                    visited[y * w + x] = 1
                    dq.append((x, y, sp[x, y][:3]))
                    changed = True
                    break
        if not changed:
            break
    while dq:
        x, y, col = dq.popleft()
        px[x, y] = (px[x, y][0], px[x, y][1], px[x, y][2], 0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx]:
                cand = sp[nx, ny][:3]
                if d2(cand, col) < STEP_TOL ** 2 or nearest_corner(cand) < GROW_REF_TOL ** 2:
                    visited[ny * w + nx] = 1
                    dq.append((nx, ny, cand))
    # 边缘羽化：与透明区相邻的不透明像素降为半透明，弱化锯齿亮边
    feather = []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] == 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] == 0:
                    feather.append((x, y))
                    break
    for x, y in feather:
        p = px[x, y]
        px[x, y] = (p[0], p[1], p[2], 120)
    return img


def main():
    names = sorted(
        name for name in os.listdir(ASSETS) if name.endswith(".png") and name != "bg.png"
    )
    for name in names:
        path = os.path.join(ASSETS, name)
        img = Image.open(path).convert("RGBA")
        frames = img.width // FRAME_W
        sheet = Image.new("RGBA", img.size, (0, 0, 0, 0))
        for index in range(frames):
            frame = img.crop((index * FRAME_W, 0, (index + 1) * FRAME_W, img.height))
            sheet.paste(key_frame(frame), (index * FRAME_W, 0))
        sheet.save(path, "PNG", optimize=True)
        # 校验：首帧顶边中点应已透明
        probe = sheet.load()[FRAME_W // 2, 3]
        print(f"{name}: {frames}帧已抠底，顶边中点 alpha={probe[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
