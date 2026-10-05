# 02 · 视觉系统规范 — Warm Paper 暖纸编辑风

> 适用范围：CreativeForge 唯一正式前端 Studio（`studio/frontend`）。
> （原 MVP 前端 `frontend/` 已于 2026-10-05 删除，见 `docs/legacy-inventory.md`。）
> 令牌单一事实来源：`studio/frontend/src/index.css` 的 `@theme` 块。
> 本文取代早期 "Forge UI 2.0 · Obsidian Arc" 暗色规范（2026-09-26 起全面切换为暖纸编辑风）。

---

## 1. 设计语言定位

- **关键词**：暖纸、墨色、宋体展示大字、发丝线、留白、几何像素插画。
- **参照**：Windup 工作台参考截图（暖纸色编辑风）+ `D:\SKILL.md` 的 gpt-taste 设计规范。
- **基本立场**：
  - 界面是"纸"，不是"屏幕"——底色永远用纸白，层级靠发丝线与深浅一档的面板色表达，**不用深色重投影卡片**。
  - 主操作色是**墨黑**（黑色主按钮 + 纸白文字），金色 `ember` 只作强调（CTA 渐变、高亮数字），不参与常规层级。
  - 展示级标题用宋体 900 字重（Noto Serif SC Black），正文与小字用 Outfit / 系统无衬线。
  - 插画为几何/像素风单色块（`CharacterArt`、`FrameFigure`），从资产数据确定性渲染，不引入照片与渐变插画。
  - 禁止：在组件中硬编码色值（一律走 token/工具类）、emoji 当图标、深色卡片堆砌、高饱和默认 Tailwind 调色板。

## 2. 色彩令牌

### 2.1 基底与线（Studio token 名 → 值）

| Token | 值 | 用途 |
| --- | --- | --- |
| `canvas` | `#f5f3ef` | 全局纸底（body 背景） |
| `surface-1` | `#edebe5` | 卡片/面板（比纸底深一档） |
| `surface-2` | `#e5e2da` | 输入框、分段控件底、行悬停 |
| `surface-3` | `#dbd7cc` | 分段控件激活块、ScoreBar 轨道、Switch 关态 |
| `line-subtle` | `#e3e0d8` | 发丝线（卡片描边、分组分隔） |
| `line` | `#d3cfc5` | 常规描边、输入框边 |
| `line-strong` | `#b9b3a5` | 强描边、基线对比条 |

（历史备注：MVP 前端删除前曾用 `paper #f5f3ef`、`panel #edebe5`、`line #e3e0d8`、`line-2 #d3cfc5`，两套名字同一 palette。）

### 2.2 文字

| Token | 值 | 用途 |
| --- | --- | --- |
| `ink` | `#1a1814` | 主文字、主色按钮底 |
| `ink-2` | `#55514a` | 次级文字 |
| `ink-3` | `#5f594f` | 说明文字、占位符强调层；保持小字号可读性 |
| `ink-4` | `#625c52` | 辅助文字（kbd、表头、时间戳）；在纸底与 surface-1/2/3 上对比度不低于 4.5:1 |

### 2.3 品牌与语义

| Token | 值 | 用途 |
| --- | --- | --- |
| `primary` | `#1a1814`（hover `#3a352d` / active `#000000`） | 主按钮、激活态、Tab 下划线、链接文字 |
| `primary-tint` | `rgba(26,24,20,.07)` | 激活底色、图标底衬 |
| `ember` | `#a9812f`（渐变终档 `#c46a3a`） | 主 CTA 渐变、高分数字、ember 徽章 |
| `success` | `#3e7d5a` | PASS、完成态 |
| `warning` | `#a9812f` | 修复轮、RETRY |
| `danger` | `#a94f3d` | 失败、危险按钮 |
| `info` | `#4a6f8a` | 信息提示 |

### 2.4 领域身份色（智能体/引擎色，纸底上加深保对比）

| Token | 值 | 领域 |
| --- | --- | --- |
| `supervisor` | `#4a6f8a` | 规划 |
| `precon` | `#0e8ea8` | 像素重建（渐变起始 `#4fb3c7`） |
| `falign` | `#7c5cc4` | 动画对齐（渐变起始 `#9d85d0`） |
| `gimport` | `#3e7d5a` | 引擎导入（渐变起始 `#5f9c7d`） |
| `qa` | `#a9812f` | 质量门 |
| `memory` | `#6f7d8c` | 记忆/检查点 |

渐变条规则：`bg-gradient-to-r from-[浅档] to-[领域色]`；ScoreRing 用 `ink → ember` 线性渐变。

## 3. 字体

| 层 | 字体栈 | 用法 |
| --- | --- | --- |
| `font-display` | `"Noto Serif SC", "Songti SC", "STSong", "SimSun", serif` | 页面 H1、英雄区大标题、品牌字 "CreativeForge"，一律 `font-black`（900） |
| `font-sans` | `"Outfit", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif` | 正文、控件、导航 |
| `font-mono` | `"JetBrains Mono", ui-monospace, Consolas, …` | ID、分数、事件流、路径（配 `.tabular`） |

字体经 `@fontsource/outfit`（400/500/600）与 `@fontsource/noto-serif-sc`（600/900）自托管加载，两个前端一致。

## 4. 形状、描边与投影

- 圆角：`xs 4 / sm 6 / md 8 / lg 10 / xl 12`；大区块 `rounded-xl`～`rounded-2xl`，控件 `rounded-md`。
- 描边优先于投影：卡片 = 1px `line-subtle` + 顶部高光（`.cf-sheen`，白色 55% 顶渐变）。
- 投影仅暖色柔影：`e2 = 0 1px 2px rgba(26,24,20,.06)`，`e3 = 0 12px 32px -12px rgba(26,24,20,.18)`；主按钮投影 `0 6px 16px -8px rgba(26,24,20,.55)`。**禁止冷黑重投影与彩色辉光。**
- 焦点环：`0 0 0 2px canvas + 0 0 0 4px rgba(26,24,20,.45)`。
- 文本选区：纸白底反白墨（`::selection` 墨底纸字）。

## 5. 动效

- 标准缓动 `--ease-standard: cubic-bezier(0.2, 0.8, 0.2, 1)`；微交互时长 150–220ms。
- 运行态脉冲 `pulse-run`（墨色波纹）；骨架屏 `shimmer`（surface-2↔surface-3）。
- framer-motion 进场：淡入 + 8–14px 位移，禁弹跳过冲。
- 全局尊重 `prefers-reduced-motion`。

## 6. 组件规范（`components/ui.tsx` 为实现基准）

- **Button**：`primary`（墨底纸字）／`ember`（金→陶土渐变，纸白字，仅用于最高优先 CTA）／`secondary`（surface-2 底 + line 描边）／`ghost`／`danger`（danger 15% 底 + 40% 描边）。
- **Card**：发丝线卡 + 可选左侧 3px 领域色条（`domain` 属性）+ 顶高光；卡头 1px `ink/[.08]` 分隔。
- **Badge**：语义色 15% 底 + 同色文字；`neutral` 用 `ink/[.06]` 底。
- **Tabs / Segmented**：Tabs 激活 = 2px 墨色下划线；Segmented 激活 = surface-3 实底块。
- **输入**：surface-2 底 + line 边，聚焦墨色描边 + 暖色 3px 柔环。
- **StatusDot**：状态色 + 同色 16% 4px 光环；running 态墨色脉冲。
- **空状态**：tint 底圆形图标 + 标题 + 说明 + 主按钮，居中排布。

## 7. 页面模式

- 页面容器：`mx-auto max-w-[1440px] px-4 py-5 md:px-6`，卡片栅格 `grid-cols-12 gap-5`。
- **PageHeader**：overline（11px 全大写 ink-3/ink-2）→ 宋体黑 H1 → 一句说明 → 右侧操作区。
- **英雄区**：纸色微渐变底（`linear #f2efe9→#ece9e2` + 金/绿径向光斑 ≤12% 透明度），宋体黑大标题。
- 表格：表头 surface-2 底全大写小字，行间 1px `ink/[.08]` 发丝线，悬停 `surface-2/60`。
- 顶栏：纸色 86% 半透明 + 背景模糊；侧栏：纸色微渐变，激活项 tint 底 + 左侧墨色竖条。
- Toast：右下角堆叠，纸白 95% 底 + 3px 语义色左条。

## 8. 主题元数据

- `color-scheme: light`；滚动条 `#d3cfc5`。
- React Flow 覆写为浅色（纸白控件、`#ddd9cf` 网格点、`#b9b3a5` 虚线边）。
- 三维视口（R3F）：背景 `#f1efe9`，地面 `#e3dfd6`，暖金点光 `#a9812f`。

## 9. 遗留说明

Studio 的 token 名（`canvas/surface/ink-2..4/primary/ember` 等）沿自旧暗色主题，**名字未改、值已全部换为暖纸**，保证组件层零迁移。新增样式时一律使用上表 token；发现硬编码色值应当场收敛。
