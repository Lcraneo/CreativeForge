# 02 · 视觉规范（Forge UI 2.0 Tokens）

> 本规范是唯一事实来源（SSOT）。实现时所有颜色、字号、间距、圆角、阴影、动效必须引用本表 Token；
> 设计稿 `mockups/mockup.css` 与本表逐项对应，评审时可直接交叉核对。

---

## 1. 色彩系统

### 1.1 基础层（Obsidian 曜石）

| Token | 值 | 用途 |
|-------|----|------|
| `--cf-canvas` | `#07090D` | 应用最底层背景 |
| `--cf-surface-1` | `#0E1219` | 卡片、面板默认底色 |
| `--cf-surface-2` | `#141922` | 内嵌区块、输入框、表头 |
| `--cf-surface-3` | `#1B2230` | hover / 选中态底 |
| `--cf-overlay` | `rgba(7,9,13,.72)` | 弹层遮罩 |
| `--cf-line-subtle` | `#1E2633` | 卡片描边、分隔线 |
| `--cf-line` | `#2A3444` | 输入框、控件描边 |
| `--cf-line-strong` | `#3A4658` | 强调描边、图表轴线 |

### 1.2 文本层

| Token | 值 | 对比度（vs surface-1） | 用途 |
|-------|----|----|------|
| `--cf-text-primary` | `#E9EEF6` | 14.8:1 | 标题、关键数据 |
| `--cf-text-secondary` | `#A7B2C4` | 8.4:1 | 正文、说明 |
| `--cf-text-tertiary` | `#76839A` | 4.9:1 ✅AA | 辅助信息、时间戳 |
| `--cf-text-disabled` | `#4C5768` | 2.6:1 | 仅禁用态（不承载信息） |

> 规范：正文与说明禁用 4.5:1 以下颜色；`text-disabled` 只用于禁用控件。

### 1.3 品牌与语义色

| Token | 值 | 用途 |
|-------|----|------|
| `--cf-primary` | `#4CC2FF` | 主操作、链接、选中焦点（Arc Blue） |
| `--cf-primary-hover` | `#7AD1FF` | 主操作 hover |
| `--cf-primary-active` | `#2FA8E8` | 主操作 pressed |
| `--cf-primary-tint` | `rgba(76,194,255,.12)` | 选中底、图表面积 |
| `--cf-ember` | `#FFB454` | 品牌强调、得分、锻造隐喻（Ember） |
| `--cf-ember-tint` | `rgba(255,180,84,.14)` | 强调底 |
| `--cf-success` | `#34D399` | 成功、PASS、纠偏后 |
| `--cf-warning` | `#FBBF24` | 警告、QA 阈值边缘 |
| `--cf-danger` | `#FB7185` | 失败、漂移、错误 |
| `--cf-info` | `#60A5FA` | 中性信息、Supervisor |

### 1.4 引擎/角色身份色（一色一域）

| 域 | Token | 色值 | 出现位置 |
|----|-------|------|----------|
| Supervisor 规划 | `--cf-domain-supervisor` | `#60A5FA` | 任务图根节点、规划事件 |
| PReCon 像素 | `--cf-domain-precon` | `#22D3EE` | 像素页、PReCon 卡片、调色板 |
| FAlign 动画 | `--cf-domain-falign` | `#A78BFA` | 动画页、帧时间轴、根运动图 |
| GImport 导入 | `--cf-domain-gimport` | `#34D399` | 导出页、包校验 |
| QA 质量 | `--cf-domain-qa` | `#FBBF24` | 质量门、阈值刻度 |
| Memory 记忆 | `--cf-domain-memory` | `#94A3B8` | 记忆检查点 |

每个域色均配 `tint = rgba(color,.12)` 底与 `ring = rgba(color,.35)` 描边。

### 1.5 渐变

| Token | 值 | 用途 |
|-------|----|------|
| `--cf-grad-brand` | `linear-gradient(135deg,#4CC2FF,#8B7BFF)` | 品牌字标、CF Score 环 |
| `--cf-grad-ember` | `linear-gradient(135deg,#FFB454,#FF7A6B)` | 得分高亮、关键 KPI |
| `--cf-sheen` | `linear-gradient(180deg,rgba(255,255,255,.04),transparent 42%)` | 卡片顶部内高光 |

---

## 2. 字体系统

### 2.1 字族

```css
--cf-font-sans: Inter, "HarmonyOS Sans SC", "PingFang SC",
                "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
--cf-font-mono: "JetBrains Mono", ui-monospace, "SFMono-Regular",
                Consolas, "Cascadia Mono", monospace;
```

- 不强制网络字体：`Inter / JetBrains Mono` 可用则用，缺失时回退系统字体，保证离线演示一致可用；
- 数字一律 `font-variant-numeric: tabular-nums`；
- 中文标题字重 ≤ 650（避免伪粗体）。

### 2.2 字号阶梯

| Token | 字号/行高 | 字重 | 字距 | 用途 |
|-------|-----------|------|------|------|
| `display-xl` | 40/48 | 650 | -0.02em | 品牌页 Hero（技术中心） |
| `display-l` | 32/40 | 650 | -0.02em | KPI 大数、CF Score |
| `h1` | 24/32 | 600 | -0.01em | 页面标题 |
| `h2` | 18/26 | 600 | -0.01em | 区块标题 |
| `h3` | 15/22 | 600 | 0 | 卡片标题 |
| `body` | 14/22 | 400 | 0 | 正文 |
| `body-sm` | 13/20 | 400 | 0 | 次级正文、表格 |
| `caption` | 12/18 | 500 | 0 | 辅助说明 |
| `overline` | 11/16 | 600 | +0.08em uppercase | 英文副标、分组名 |
| `mono` | 13/20 | 450 | 0 | ID、路径、数据 |
| `kpi` | 32/40 | 650 | -0.02em | 数据卡数字 |

> 取消 `pixel-title` 全站铺开；像素母题只保留在品牌字标与 Pixel Studio 画布。

---

## 3. 空间、圆角与描边

### 3.1 间距（4px 栅格）

`2 / 4 / 6 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64`

| 场景 | 值 |
|------|----|
| 组件内间距（按钮/输入） | 12 / 16 |
| 卡片内边距 | 16（紧凑）/ 20（默认）/ 24（Hero） |
| 卡片间距 | 16 / 20 |
| 区块间距 | 24 / 32 |
| 页面上下留白 | 24（桌面）/ 16（移动） |

### 3.2 圆角

| Token | 值 | 用途 |
|-------|----|------|
| `radius-xs` | 4 | 色块、进度条端点 |
| `radius-sm` | 6 | 徽章、标签 |
| `radius-md` | 8 | 按钮、输入框、图标容器 |
| `radius-lg` | 12 | 卡片（默认） |
| `radius-xl` | 16 | Hero 卡片、弹层 |
| `radius-full` | 999 | 胶囊、状态点 |

### 3.3 高度（Elevation）

| Token | 值 | 用途 |
|-------|----|------|
| `e0` | `1px solid line-subtle` | 平面卡片 |
| `e1` | `e0 + sheen 内高光` | 默认卡片 |
| `e2` | `0 1px 2px rgba(0,0,0,.5) + 1px line` | 悬浮控件、下拉 |
| `e3` | `0 12px 32px -8px rgba(0,0,0,.7)` | 弹层、命令面板 |
| `glow-running` | `0 0 0 1px rgba(76,194,255,.35), 0 0 24px -4px rgba(76,194,255,.4)` | 运行中节点 |
| `focus` | `0 0 0 2px canvas, 0 0 0 4px rgba(76,194,255,.55)` | 键盘焦点环 |

---

## 4. 动效规范

| Token | 时长 | 用途 |
|-------|------|------|
| `dur-instant` | 80ms | 按压、勾选 |
| `dur-fast` | 120ms | hover / 颜色过渡 |
| `dur-base` | 180ms | 进入、展开、数值变化 |
| `dur-slow` | 280ms | 页面切换、抽屉 |
| `dur-count` | 400ms | KPI 数字滚动 |

| 曲线 | 值 |
|------|----|
| `ease-standard` | `cubic-bezier(.2,.8,.2,1)` |
| `ease-emphasized` | `cubic-bezier(.2,.9,.1,1)` |
| `ease-exit` | `cubic-bezier(.4,0,1,1)` |

**固定模式**
- 进入：`opacity 0→1` + `translateY(6px→0)`，180ms；
- 列表错峰：每项延迟 40ms，最多 6 项；
- 运行中状态点：呼吸脉冲 1.6s 循环（透明度 .4→1）；
- 任务图连线：虚线流动 1.2s linear infinite；
- 数值：ScoreBar 宽度 280ms，KPI 数字 400ms；
- `prefers-reduced-motion: reduce` 时禁用位移与脉冲，仅保留透明度过渡。

---

## 5. 布局与栅格

| Token | 值 |
|-------|----|
| `rail` 图标栏 | 64px |
| `sidebar` 展开侧栏 | 240px |
| `topbar` | 56px |
| `content-max` | 1440px |
| `gutter` | 24px（<768px 为 16px） |
| 栅格 | 桌面 12 列 / 间距 24；平板 8 列 / 16；手机 4 列 / 16 |
| 右栏 | 320px（数据面板），<1280px 时移到底部 |

### 断点行为

| 断点 | 侧栏 | 顶栏 | 栅格 | 任务图 | 表格 |
|------|------|------|------|--------|------|
| ≥1280 桌面 L | 展开 240 | 完整（面包屑+状态+⌘K） | 12 列 | 画布+右栏并排 | 标准 |
| 1024–1279 桌面 | 展开 240 | 完整 | 12 列 | 右栏落至底部 | 标准 |
| 768–1023 平板 | 图标栏 64 | 简化（状态+菜单） | 8 列 / 两栏 | 全宽画布，面板堆叠 | 隐藏次要列 |
| <768 手机 | 抽屉 + 底部 Tab | 标题+状态 | 4 列 / 单栏 | 画布横向滚动 | 转卡片列表 |

底部 Tab（手机）：工作台 / 智能体 / 资产 / 基准 / 导出。

---

## 6. 组件规格

### 6.1 Button
- 高度：`sm 28 / md 34 / lg 40`；内边距 `12 / 16 / 20`；圆角 8；字号 `body-sm/body`；
- 变体：
  - `primary`：Arc 底 + 深墨字（`#05121C`），**全站唯一主 CTA 颜色**；
  - `secondary`：`surface-2` 底 + `line` 描边；
  - `ghost`：透明，hover `surface-3`；
  - `danger`：`danger` 底或 danger-tint 描边；
  - `ember`：仅用于「生成资产」等创造型 CTA 的品牌强调（每屏 ≤1 个）；
- 状态：hover 120ms → active `translateY(1px)` → loading（16px spinner，按钮宽度不变）→ disabled 45% + `not-allowed`；
- 必带 `focus-visible: focus ring`。

### 6.2 Input / Textarea / Select
- 高 36（大号 44 用于任务描述）；圆角 8；底 `surface-2`；描边 `line`；
- focus：描边 `primary` + 3px `primary-tint` 外环；
- placeholder `text-tertiary`；错误描边 `danger` + 12px 错误文案；
- 字符计数与快捷键提示右对齐。

### 6.3 Card
- 圆角 12（Hero 16）；底 `surface-1`；描边 `line-subtle`；内高光 `sheen`；
- 头部 44px：`h3` 左 + 操作右；正文 padding 20（紧凑 16）；
- 可交互卡片 hover：描边 `line`、上移 1px、120ms；
- 域色卡片：左缘 3px 域色条或头部小色点，二者只选其一。

### 6.4 Badge / StatusDot / Chip
- Badge：高 22，圆角 6，字号 12/500，语义 tint 底 + 300 级文字；
- StatusDot：8px 圆点 + 4px 同色 halo；`running` 呼吸脉冲；
- Chip（引擎/标签）：胶囊、`surface-2` 底、图标+文案，可选中（`primary-tint` + `primary` 描边）。

### 6.5 ScoreBar
- 轨道 6px `surface-3`，填充按值：≥阈值 成功色，低于 危险色，无阈值 主色；
- 阈值刻度：2px `text-tertiary` 竖线，带 tooltip；
- 数值右对齐 mono + tabular；宽度过渡 280ms；
- 必须同时提供数值文本（不依赖颜色）。

### 6.6 KV 行
- 行高 30，上下 `line-subtle` 分隔；label 12 `text-tertiary`；value mono 13 `text-primary`；
- 长文本溢出 `ellipsis` + title；可复制值带复制按钮（hover 出现）。

### 6.7 Tabs / Segmented
- Tabs：下划线 2px `primary`，选中字 600，含计数徽章；
- Segmented（引擎切换等）：容器 `surface-2` + 4px 内边距，选中块 `surface-3` + 内高光 + 域色图标。

### 6.8 Stepper / Pipeline
- 节点：28px 圆形或 24px 图标块；连线 2px；
- 状态：pending `line` / running `primary` 脉冲 / done `success` 对勾 / failed `danger` 叉；
- 横向用于 GImport 流程、导出流程；纵向用于 Agent 时间线。

### 6.9 数据表 / 列表
- 表头：`overline` `text-tertiary`，高 36，底 `surface-2`；
- 行高 44，hover `surface-2`，分隔 `line-subtle`；数字右对齐 tabular；
- 空表：EmptyState；>50 行分页或虚拟滚动。

### 6.10 反馈组件
- **EmptyState**：40px 域色图标块 + `h3` 标题 + 12px 说明 + 主 CTA；
- **Skeleton**：`surface-2` 基底 + 1.4s shimmer，形状与真实内容一致；
- **Toast**：右下 320px，`e3`，顶部 2px 语义色条，4s 自动关闭；
- **Tooltip**：400ms 延迟，`e3`，12px；
- **Command Palette**：⌘K 唤起，560px 居中，分组（导航/操作/最近任务），键盘 ↑↓ Enter；
- **Event Stream**（Agent 页）：`aria-live="polite"`，等宽 12px，按事件类型着色 + 图标。

### 6.11 图标
- 线性风格，20px / 描边 1.75（密集区 16px）；统一圆角端点；
- 核心图标集：`spark(生成)` `cube(资产)` `grid(像素)` `film(动画)` `package(导入/导出)` `gauge(基准)` `activity(事件)` `terminal(日志)` `check` `alert` `x` `chevron` `search` `command` `panel(折叠)` `download` `play/pause`；
- 禁止 emoji 充当功能图标。

---

## 7. 可访问性（A11y）

| 项 | 要求 |
|----|------|
| 对比度 | 正文/说明 ≥4.5:1；大字与图标 ≥3:1；禁用态除外 |
| 焦点 | 所有可交互元素 `:focus-visible` 显示焦点环，顺序符合阅读流 |
| 键盘 | Tab / Shift+Tab / Enter / Space / Esc / ⌘K / 方向键（Tabs、Segmented） |
| 状态 | 颜色 + 图标 + 文案三重表达，色弱可辨 |
| 动态 | 运行状态用 `aria-live="polite"` 播报；数值变化附文本 |
| 命中区 | 最小 32×32；移动端 44×44 |
| 动效 | 遵循 `prefers-reduced-motion` |
| 语义 | 正确使用 `header/nav/main/section`、`aria-label`、`role="status"` |

---

## 8. 数据可视化规范

- 序列色序：Arc → Ember → PReCon 青 → FAlign 紫 → GImport 翠 → Info；
- 基线（Baseline）统一 `text-tertiary` 灰条；方法（Method）用语义色，形成"灰 vs 彩"的对比叙事；
- 网格线 `line-subtle` 虚线 1px；轴线 `line-strong`；
- 提升值：正向 `success`，负向 `danger`，徽章同时给出符号与百分比；
- 禁止 3D 饼图、双 Y 轴；环形仅用于单一总分（CF Score）；
- 所有图表必须可直接读到原始数值（标签或表格）。
