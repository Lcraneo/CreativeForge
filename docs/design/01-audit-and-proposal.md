> **历史说明（2026-10-30）**：本文件记录旧版 Forge UI 的审计或视觉方案，现已被仓库根目录的 `PRODUCT.md` 与 `DESIGN.md` 取代。新增界面请以新文档为准，本文件仅保留为历史决策证据。

# 01 · 设计审计与升级方案

> 产品：CreativeForge AI — AI 游戏资产生成工厂（Studio 控制台）
> 交付代号：**Forge UI 2.0「Obsidian Arc / 曜石弧光」**
> 适用范围：`studio/frontend`（React 18 + TS + Vite + Tailwind v4）

---

## 1. 现状审计

### 1.1 视觉语言

| # | 问题 | 证据 |
|---|------|------|
| V1 | 颜色体系未落地：`index.css` 定义了 `--cf-*` 变量但全项目没有任何地方引用，页面全部硬编码 `zinc / sky / cyan` 工具类 | `src/index.css:3-11`，各页面 className |
| V2 | 主色不统一：同为主操作，工作台/动画页用 `cyan-400`，导出页用 `emerald-400`，下载按钮用 `sky-500` | `Workspace.tsx:84`、`ExportCenter.tsx:89`、`ExportCenter.tsx:103` |
| V3 | 引擎身份色缺失：PReCon / FAlign / GImport 在界面中没有稳定的色彩标识，无法形成"技术品牌"记忆 | 全站 |
| V4 | 层次感弱：卡片统一 `bg-zinc-900/50` 单层，无 elevation / 内发光 / 顶部高光，信息分区靠边框硬切 | `ui.tsx:16` |
| V5 | 圆角混乱：卡片 `rounded-xl`、按钮 `rounded-lg`、徽章 `rounded`、色块 `rounded`，无半径阶梯 | `ui.tsx:16,45,72` |

### 1.2 排版与字体

| # | 问题 | 证据 |
|---|------|------|
| T1 | 无字号阶梯：从 `text-[10px]` 到 `text-5xl` 随意取值，正文混用 12/13/14px | `Workspace.tsx:49`、`AgentDashboard.tsx:104` |
| T2 | Hero 标题 `text-5xl font-black` 与产品工具定位不符，挤压首屏操作区 | `Workspace.tsx:49-51` |
| T3 | `pixel-title` 只是大写+字距，用于所有卡片标题，视觉噪音大且不是真像素字体 | `index.css:18-21`、`ui.tsx:20` |
| T4 | 中英混排无规范：标签、副标题、说明中英夹杂且缺少层级区分 | 各页面 |
| T5 | 数据与正文未分离：只有零散 `font-mono`，缺少表格数字、tabular-nums 规范 | `ui.tsx:70,86` |

### 1.3 布局与空间

| # | 问题 | 证据 |
|---|------|------|
| L1 | 页面容器不统一：`max-w-6xl px-8 py-14` / `max-w-5xl px-6 py-6` / `max-w-3xl px-8 py-16` 三种规格 | Workspace / Pixel / 空状态 |
| L2 | 侧边栏固定 224px 纯文字导航，无图标、无分组、无折叠；技术中心有路由但不在导航中 | `Layout.tsx:16-47`、`App.tsx:23` |
| L3 | 无响应式：`grid-cols-5`、`grid-cols-[1fr_340px]`、`grid-cols-3` 全部硬编码，窄屏直接溢出 | `BenchmarkCenter.tsx:88`、`AgentDashboard.tsx:163`、`AssetInspector.tsx:38` |
| L4 | 空间节奏失衡：Hero 上下留白过大，数据密集页留白过小，缺少统一的 4px 栅格纪律 | 对比 Workspace 与 Benchmark |
| L5 | 事件流、时间线、QA 三卡纵向堆叠在 340px 列内，滚动区域各自为政 | `AgentDashboard.tsx:180-255` |

### 1.4 交互反馈与状态

| # | 问题 | 证据 |
|---|------|------|
| I1 | 无 `focus-visible` 焦点样式，键盘用户完全不可用 | 全站 |
| I2 | 按钮只有 `hover` + `disabled:opacity-40`，无 active / loading / 成功反馈 | 各页面 |
| I3 | 空状态、加载、错误均为裸文本，无插画、无引导操作 | `AgentDashboard.tsx:123-140` 等 |
| I4 | 状态仅靠颜色区分（对比色弱不友好），且事件流无 `aria-live` | `AgentDashboard.tsx:196-210` |
| I5 | Emoji 充当图标（⚡ / ⬇ / ✓），渲染不一致、不专业 | `Workspace.tsx:86`、`ExportCenter.tsx:91` |
| I6 | 过渡动画缺失统一曲线/时长，只有零散 framer-motion 默认值 | 全站 |

### 1.5 可访问性（实测）

| # | 问题 | 计算 |
|---|------|------|
| A1 | `text-zinc-500`(#71717a) 在 `zinc-950`(#09090b) 上对比度约 **4.1:1**，低于 AA 小字 4.5:1 要求 | 全站说明文字 |
| A2 | 大量 `text-[10px]`/`text-[11px]` 小字，低于 12px 可读下限 | `Layout.tsx:38,44` 等 |
| A3 | 三个 10 行内联页面（TechnologyCenter）未跟随设计语言，属于明显短板 | `TechnologyCenter.tsx` |

### 1.6 结论

当前 UI 属于"能用但不成体系"的比赛原型：**颜色、字体、间距、状态、反馈五套语言各自为政**。升级不需要推翻信息架构，而需要建立一层完整的设计系统（Tokens → Primitives → Shell → Pages → Motion），并统一实施。

---

## 2. 产品定位与设计目标

**定位**：面向独立游戏团队与资产外包团队的「AI 资产生产控制台」。用户是开发者/TA/美术，不是普通消费者。

**品牌气质（5 个关键词）**
1. **精密 Precise** — 像素级对齐是产品承诺，界面也必须像素级对齐；
2. **工程感 Engineered** — 像监控台/IDE，而不是营销落地页；
3. **锻炉 Forge** — 深色曜石底 + 弧光青 + 余烬橙，传达"把创意锻造成资产"；
4. **可信 Verifiable** — 数据、阈值、校验结果必须清晰可读（Benchmark 是卖点）；
5. **克制 Restrained** — 动效服务于状态，不喧宾夺主。

**设计目标（可验收）**
- 全站无硬编码颜色/字号/间距，100% 走 token；
- 页面容器、标题、卡片、按钮规格全站一致；
- 覆盖 4 档断点（≥1536 / 1024–1535 / 768–1023 / <768），无溢出；
- 正文对比度 ≥ 4.5:1，关键操作具备键盘焦点环与反馈；
- 首屏可完成"输入目标 → 开始生产"闭环，视觉重心从口号转向操作。

---

## 3. 设计方向：「曜石弧光 Obsidian Arc」

> **深空曜石为底，一道弧光贯穿：青蓝代表算力与精密，余烬橙代表锻造与创造。**

- **基色**：带蓝调的近黑曜石（`#07090D`），而不是中性 zinc 灰，屏幕观感更"电子"；
- **主色**：Arc Blue `#4CC2FF`（沿用并提纯现有 sky 色，保证品牌连续性）；
- **辅色**：Ember `#FFB454`（CTA 强调、得分高亮、品牌图形）；
- **引擎色**：PReCon 青 / FAlign 紫 / GImport 翠，形成"技术三原色"，贯穿导航、卡片、图表；
- **材质**：分层表面（4 级 elevation）+ 1px 冷色描边 + 顶部内高光（`inset 0 1px 0 rgba(255,255,255,.04)`），营造"玻璃仪器面板"质感；
- **图形**：品牌区使用 8-bit 像素网格母题（呼应像素重建），以 CSS/SVG 实现，不用 emoji。

---

## 4. 设计原则（供评审与实现裁决）

| 原则 | 含义 | 反例（现状） |
|------|------|--------------|
| P1 操作优先 | 首屏最大视觉权重给输入与主 CTA，品牌口号退居其次 | text-5xl 口号占据首屏 |
| P2 一色一义 | 每个颜色只表达一类语义：主色=操作，引擎色=技术域，语义色=状态 | 导出页绿色按钮、下载蓝色按钮 |
| P3 数据至上 | 数字用 tabular-nums，阈值有刻度，对比有基线 | ScoreBar 无刻度、无百分比动画 |
| P4 状态可读 | 成功/运行/失败 = 颜色 + 图标 + 文案三重表达 | 仅颜色徽章 |
| P5 一屏一节奏 | 所有页面共用同一个 Shell、容器、标题与间距节奏 | 三种容器宽度 |
| P6 动效克制 | 120/180/280ms 三档时长，只做进入、状态切换与注意力引导 | 无统一动效语言 |

---

## 5. 信息架构调整

现有 8 个路由保持 URL 不变，导航按工作流分 4 组 + 补上缺失的技术中心入口：

```
生产 Create      工作台 /            智能体 /agents
资产 Assets      资产 /asset         像素 /pixel        动画 /animation
交付 Deliver     导出 /export
洞察 Insights    基准 /benchmark     技术 /technology
```

Shell 升级：
- 侧栏 240px（可折叠为 64px 图标栏，状态持久化到 localStorage）；
- 顶部 56px 命令栏：面包屑 + 全局任务状态 + ⌘K 命令面板入口 + 当前资产；
- 内容容器统一 `max-width: 1440px`，双侧 gutter 24px（<768px 为 16px）。

---

## 6. 交付物与实施路线

本评估包包含：

| 交付物 | 文件 | 说明 |
|--------|------|------|
| 设计审计与方案 | `docs/design/01-audit-and-proposal.md` | 本文 |
| 视觉规范 | `docs/design/02-visual-spec.md` | Tokens / 组件 / 动效 / 响应式 / A11y |
| 关键界面说明 | `docs/design/03-key-screens.md` | 8 个页面的布局与交互规格 |
| 高保真设计稿 | `docs/design/mockups/review.html` + `mockup.css` | 可在浏览器直接预览的完整设计板 |

**实施方案（评审通过后执行）**

| 阶段 | 内容 | 验收 |
|------|------|------|
| S1 Tokens | 重写 `index.css`：CSS 变量 + Tailwind v4 `@theme`；字体栈 | 全站可用 `bg-surface-1 / text-primary / border-subtle` 等语义类 |
| S2 基础组件 | 重构 `ui.tsx`：Button / IconButton / Input / Select / Card / Badge / StatusDot / ScoreBar / KV / Tabs / Tooltip / EmptyState / Skeleton / Toast + 图标集 | Storybook 式预览页（设计稿即规格） |
| S3 Shell | 重构 `Layout.tsx`：分组导航 + 图标 + 折叠 + Topbar + 响应式抽屉 | 4 档断点无溢出 |
| S4 页面 | Workspace → Agent → Asset → Pixel → Animation → Benchmark → Export → Technology 逐一改造 | 与设计稿逐屏比对 |
| S5 动效与 A11y | 统一 motion token；焦点环、aria-live、对比度检查 | Lighthouse A11y ≥ 95 |
| S6 回归 | `tsc -b && vite build` + 现有 36 项后端契约测试不受影响 | 构建零错误 |

**本次交付的验收清单**
- [x] 设计稿可在浏览器完整预览（含视觉基础、四个关键界面、响应式示意）
- [x] 预览页与规范中所有色值/字号/间距/圆角一一对应
- [x] 关键界面覆盖 加载 / 空 / 失败 / 成功 四类状态
- [x] 响应式示意覆盖 1440 / 1024 / 390 三档

---

## 7. 实施状态（2026-09-25）

S1–S6 已完成并构建验证通过：

| 阶段 | 产物 | 状态 |
|------|------|------|
| S1 Tokens | `src/index.css` Tailwind v4 `@theme`：颜色/字体/圆角/高度/动效/滚动条/React Flow 暗色主题 | ✅ |
| S2 组件 | `components/ui.tsx`（Button/Card/Badge/StatusDot/Chip/Input/Textarea/Segmented/Tabs/ScoreBar/ScoreRing/KV/Stat/Stepper/Spinner/Skeleton/EmptyState）+ `icons.tsx`（24 图标）+ `Toaster.tsx` + `stores/toastStore.ts` | ✅ |
| S3 Shell | `Layout.tsx`（分组导航 / 折叠 / 全局任务状态 / 移动端底部 Tab）+ `CommandPalette.tsx`（⌘K 命令面板） | ✅ |
| S4 页面 | 8 个页面全部按设计稿改造：Workspace / Agent / Asset / Pixel / Animation / Benchmark / Export / Technology | ✅ |
| S5 动效与 A11y | 焦点环、aria-live 事件流、reduced-motion、对比度达标、Toast 反馈 | ✅ |
| S6 回归 | `tsc -b && vite build` 零错误；后端 36 项契约测试 0 失败 | ✅ |

附带修复了两个既有缺陷：`useAssetLoader` 因 loading 依赖自取消导致资产页永远空态；Benchmark 对比徽章缺少负号。

