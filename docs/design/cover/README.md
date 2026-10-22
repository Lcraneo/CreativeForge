# CreativeForge AI · 项目封面（「纸上锻坊」）

> 2026-10-06 交付。源文件 `cover.html`（四种版式单页）+ 渲染脚本 `render.py`，成品在 `exports/`。
> 设计令牌与 `studio/frontend/src/index.css @theme` 同源，字体复用 studio 自托管 @fontsource，与产品视觉零偏差。

## 设计概念

封面是一张工坊「锻单」：一句自然语言目标写在纸上，经三道工序印——
**塑**（PReCon 像素重建）、**律**（FAlign 动画对齐）、**铸**（GImport 引擎导入）——
锻出像素法师资产（呼应 README 演示目标"像素 RPG 火焰法师"），由朱印「锻」钤印认证为 GAME-READY。

品牌元素全部取自「纸上工坊」体系：暖纸底 + 天光/金晕 + 纸纹肌理、发丝装帧框（框角 ember 菱形角标）、
宋体 900 展示大字、墨印（实底）/朱印（ember 描边）印章系统、领域色工序印、暖色柔影。
配色：纸 `#f5f3ef` / 墨 `#1a1814` / 金 `#a9812f`，工序印用 PReCon 青 `#0e8ea8`、FAlign 紫 `#7c5cc4`、GImport 绿 `#3e7d5a`。

## 成品清单（exports/）

| 文件 | 尺寸 | 用途 |
| --- | --- | --- |
| `creativeforge-cover-16x9.png` | 1920×1080 | 数字主视觉：路演大屏、演示封面、视频片头 |
| `creativeforge-cover-a4-print.pdf` | A4 矢量（字体内嵌、可提取文本） | **印刷母版**：无损缩放，交印首选 |
| `creativeforge-cover-a4-print.png` | 2480×3508（A4 @300dpi） | 印刷/打样位图；海报纸、展板 |
| `creativeforge-cover-square.png` | 1080×1080 | 社媒方图：朋友圈/小红书/头像式场景 |
| `creativeforge-cover-banner.png` | 1500×500 | 横幅：GitHub 仓库头图、公众号封面 |

## 再生成

```bash
cd docs/design/cover
python render.py          # 全量出图（依赖 playwright + chromium）
python render.py --draft  # 仅 16:9/A4 低倍率小样，排版自查用
```

- 字体经 `file://` 直读 `studio/frontend/node_modules/@fontsource/`（Noto Serif SC 900/600、Outfit 400/500/600），
  若在其它机器渲染需先在 studio/frontend 装依赖，或改 cover.html 里的字体链接路径。
- PNG 倍率在 `render.py` 的 `BOARDS` 里调（16:9 与 1:1、横幅 ×2，A4 ×2480/794 ≈ 300dpi）。
- 印刷提示：成品为无边距（full-bleed 视觉靠纸底色延展）版式；若印厂要求 3mm 出血，
  用 PDF 版让印方等比扩印即可——纸底为纯色 `#f5f3ef`，扩边无接缝风险。

## 修改指引

四种版式共用同一套 CSS 令牌与组件类（`.seal-ink` / `.seal-ember` / `.seal-domain` / `.pixel-art`），
改一处全局生效；各版式独立类名前缀 `a-` / `b-` / `c-` / `d-`。像素法师的画布在文件底部 `MAGE` 字符数组，
`X` 墨 / `E` 金 / `F` 脸纸白 / `C` 眼墨，每行定长 16 字符。
