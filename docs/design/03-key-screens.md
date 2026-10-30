> **历史说明（2026-10-30）**：本文件记录旧版 Forge UI 的审计或视觉方案，现已被仓库根目录的 `PRODUCT.md` 与 `DESIGN.md` 取代。新增界面请以新文档为准，本文件仅保留为历史决策证据。

# 03 · 关键界面设计说明

> 配套设计稿：`docs/design/mockups/review.html`（浏览器打开即可对照评审）。
> 每个界面包含：目标 → 布局 → 层级 → 状态 → 交互 → 响应式。

---

## 0. 全局应用框架（App Shell）

```
┌──────┬─────────────────────────────────────────────────────────────┐
│      │ Topbar 56  · 面包屑 / 当前资产 / 全局状态 / ⌘K / 折叠        │
│ Side ├──────────────────────────────────────────────┬──────────────┤
│ bar  │  Content  max 1440 · gutter 24               │  Context     │
│ 240  │  页面标题区（h1 + 描述 + 页面级操作）         │  Rail 320    │
│      │  区块（Card 栅格）                            │ （按页可选） │
├──────┴──────────────────────────────────────────────┴──────────────┤
│ （<768px）底部 Tab：工作台/智能体/资产/基准/导出                    │
└─────────────────────────────────────────────────────────────────────┘
```

**侧栏**
- 品牌区：SVG 像素锻锤标记 + 字标 `CreativeForge`（`h3`）+ `overline` 副标 `AI ASSET FACTORY`；
- 分组导航（`overline` 分组名 + 24px 图标 + 中文主标 + 快捷键角标）：
  - 生产：工作台、智能体
  - 资产：资产、像素、动画
  - 交付：导出
  - 洞察：基准、技术
- 选中态：`primary-tint` 底 + 左侧 2px 域色指示条 + 图标着色；hover `surface-3`；
- 底部：版本号 + 引擎健康状态点（三引擎在线）；
- 折叠：240 ↔ 64（仅图标），状态存 localStorage，`panel` 图标切换。

**顶栏**
- 左：面包屑（分组 / 页面）；
- 中：全局任务状态条（`StatusDot` + 任务 ID + 进度 + 跳转）；
- 右：资产切换器、⌘K 按钮（显示快捷键）、折叠按钮。

---

## 1. 工作台 Workspace（/） — 生产入口

**目标**：5 秒内完成"描述 → 开始生产"；同时展示系统产出能力与最近任务。

**布局**（12 列）
```
行1  Hero 16 列宽（全宽 Card，圆角 16，sheen + 弧形品牌光晕）
     ├─ 左（8列）：h1「今天要锻造什么资产？」+ 副标
     │    Textarea（44 高，6 行）+ 4 个示例 Chip + 字符计数
     │    底部：[引擎 Chip 组 Unity/Cocos/Godot] [Generate 主 CTA（Ember）]
     └─ 右（4列）：生产管线 Stepper（Generation→PReCon→FAlign→GImport→QA，横向 5 节点）
行2  KPI 行（4 × 3列）：CF Score 96.6 / PReCon 像素一致性 90% / FAlign 漂移 0.00 / 导入成功率 100%
     —— 数字 display-l + 迷你趋势线 + 点击跳转对应页面
行3  最近任务 Card（全宽）：表格式列表（ID / 目标 / 状态 / 资产 / 时间 / 操作）
行4  技术三卡（3 × 4列）：PReCon / FAlign / GImport，域色左缘条 + 一句话说明 + "查看技术细节 →"
```

**层级**：Hero 输入 > 主 CTA > KPI > 任务列表 > 技术卡。品牌口号降为 Hero 内一行 `body-sm`，不再占满首屏。

**状态**
- 空任务：任务 Card 内 EmptyState（`cube` 图标 + "还没有生产记录" + 示例按钮）；
- 生成中：CTA 变 loading，Hero 底部出现流水线 Stepper 动画，自动跳转智能体页。

**交互**
- `/` 聚焦输入；`⌘+Enter` 提交；
- 示例 Chip 点击填充并聚焦；
- 引擎 Chip 为多选偏好（写入 goal 元数据，UI 上高亮）；
- 成功创建：Toast「任务 T0007 已进入规划」+ 侧栏全局状态条出现。

**响应式**：<1280 KPI 2×2；<1024 Hero 单列（管线图折叠为横向可滚动）；<768 隐藏管线图与技术卡，CTA 吸底全宽。

---

## 2. 智能体指挥中心 Agent Dashboard（/agents） — 生产可视

**目标**：让"多智能体自主规划"可见、可信、可追踪。

**布局**
```
页头：h1 + 目标全文（可展开）+ 任务 ID + 总状态 Badge + 进度环
主体 grid: [1fr, 320px]（<1280 右栏落底）
左：任务图 Card（画布 min 420，React Flow）
    自定义节点：32px 域色图标块 + 名称(h3) + 副标(agent/kind) + 状态环
    节点状态：idle 描边 line / running primary 脉冲 glow / done success / failed danger
    连线：line-strong，流动虚线；布局分层：Supervisor → 专家链 → QA → Memory
右：Tabs（事件流 / 时间线 / 质量）
    事件流：等宽 12px，时间 + 事件类型图标 + agent，自动滚动，aria-live
    时间线：2px 竖轨 + 状态点 + 事件标题 + 相对时间
    质量：CF/QA 分节 ScoreBar + 阈值刻度 + 修复轮记录
底部（有条件）：修复轮提示条（warning tint）「第 1 轮修复：pixel 0.78 → 0.90」
```

**交互**：节点 hover 显示 tooltip（能力、耗时、产物）；节点点击将右栏切到对应事件；图支持缩放/适配；`f` 适配视图。

**状态**
- 无任务：EmptyState + 主 CTA 回工作台；
- 运行中：顶栏全局状态同步，运行节点脉冲；
- 失败：失败节点 danger + 右栏展示错误与恢复动作（重试 / 降级引擎 / 人工介入）；
- 完成：任务图整体 success，出现「查看资产 Inspector →」主 CTA。

**响应式**：<1024 画布全宽、面板两列网格；<768 面板单列、画布允许平移缩放。

---

## 3. 资产检查器 Asset Inspector（/asset） — 协议数据全貌

**目标**：一屏看懂 CreativeAsset 五段协议（Identity / Pixel / Animation / Engine / Quality）。

**布局**
```
页头：资产名 + ID + 引擎 Badge + 操作（导出 / 重新生成）
左栏 4列：Identity Card（KV ×5 + 3D Viewer 240 高，圆角 12）
          + Quality 总分 Card（环形 CF Score + 三阈值刻度）
中栏 4列：PReCon Card（KV + 调色板缩略 + ScoreBar，域色青）
          FAlign Card（KV + 帧缩略条 + 漂移纠偏状态，域色紫）
右栏 4列：GImport Card（资源清单 Badge 组 + 校验 Checklist）
          + QA Gate Card（分区 ScoreBar + 阈值图例 + 修复记录）
```

**细节**
- 校验 Checklist：`check`/`x` 图标 + 名称 + 右侧详情，失败项可展开；
- 调色板缩略：8×2 色块（4px 圆角），hover 显示 hex 并可复制；
- 帧缩略条：横向 filmstrip，当前帧高亮，支持左右方向键切换；
- 所有 ScoreBar 显示数值 + 阈值刻度；分数附带「阈值 pixel 0.80」说明。

**状态**：无资产 EmptyState（生成引导）；3D 加载 skeleton；QA 未报告显示「待验证」。

**响应式**：≥1280 三栏（4/4/4）；1024–1279 两栏（左 Identity 独立，其余 2 列）；<768 单栏，3D Viewer 高 200。

---

## 4. Pixel Studio（/pixel） — PReCon 重建对比

**目标**：直观展示"AI 原图 → 语义 16 色像素"的质变。

**布局**
```
页头：h1 + 说明 + Segmented「Before · AI 原图 / After · PReCon」+ 缩放
左 6列：对比画布 Card：Stage 放大网格（26px/格），After 显示网格线与 2px 间隙，
        可拖动分割线对比（Clip-path）；底部 Badge：色数 / 网格对齐 / 置信度
右 6列：
  ├ 语义调色板 Card：8×2 色块 + 语义角色列表（outline/base/shadow/highlight，可复制）
  ├ 网格推断 Card：3×3 采样点示意 SVG + KV（网格尺寸/置信度/颜色数）
  └ 质量 Card：pixel overall ScoreBar（阈值 0.80）+ 检查项
```

**交互**：Before/After 用键盘 ←→ 切换；色块点击复制 hex（Toast 反馈）；分割线拖动实时更新占比。

**响应式**：<1024 单列，画布居中并限制最大宽度；<768 画布支持双指缩放提示。

---

## 5. Animation Studio（/animation） — FAlign 对齐可视化

**目标**：证明"漂移 → 纠偏"与"时序平滑"。

**布局**
```
页头：h1 + 说明 + Badge（action / frames / fps / drift corrected）
左 8列：预览舞台 Card（域色紫氛围光晕，居中火柴人 + 相位指示）
        帧时间轴 Card：横向 filmstrip，选中帧 primary 描边 + 抬起 2px
        根运动 Card：折线图（红=对齐前漂移，绿点=纠偏后），基线虚线，hover 显示第 N 帧 dx
右 4列：质量 Card（Anchor/Motion/Temporal/Overall ScoreBar + 阈值）
        对齐说明 Card（锚点四点、相位序列、纠偏帧数）
```

**交互**：空格播放/暂停；←→ 逐帧；拖动时间轴滑块；轨迹图 hover 十字准线；帧卡片点击暂停并选中。

**响应式**：<1280 质量卡落底两列；<768 单列，时间轴横向滚动吸附。

---

## 6. 基准中心 Benchmark Center（/benchmark） — 数据说服力

**目标**：用真实数据证明自研引擎优于基线；这是对外汇报的"证据页"。

**布局**
```
页头：h1 + 数据集说明（12 资产 / 6 类别 / 8 动画）+ 导出报告按钮
行1：左侧 CF Score Card（4列，环形 96.6，渐变 brand，四分量 ScoreBar）
     右侧 三引擎对比 Card（8列）：
       PReCon：像素一致性 81%→90%、轮廓、颜色数 37→16（基线灰条 vs 方法彩条）
       FAlign：根漂移 2.25→0.00、脚步稳定、时序平滑 85%→96%
       GImport：成功率 100%、45× 提速、12 步→1 步
行2：Agent 统计 Card（完成率/规划正确率/恢复率 + 12/12 说明）
     引擎覆盖 Card（Unity/Cocos/Godot 图标 + 导出验证状态）
行3：方法学脚注（数据集、阈值、可复现命令）
```

**细节**：对比行结构统一为 `指标名 | 基线条(灰) | 方法条(域色/成功色) | 提升徽章`；提升徽章带符号与百分比；数字 tabular；进入时条宽 0→目标 280ms 错峰 40ms。

**状态**：加载 skeleton 三条；失败 ErrorState + 重试；报告时间戳展示在页头右侧。

**响应式**：<1280 行1 改两行（CF 卡全宽 / 对比卡堆叠）；<1024 对比行改为两列卡片（基线 vs 方法）；<768 单列，表格横向滚动。

---

## 7. 导出中心 Export Center（/export） — 最后一公里

**目标**：引擎选择 → 导出 → 校验 → 下载，四步清晰闭环。

**布局**
```
页头：h1 + 说明
左 8列：流程 Card：Stepper（Asset→Manifest→Atlas→Animation→Prefab→Package）
        引擎选择 Card：三张 Segmented 卡（Unity/Cocos/Godot，域色图标，含"上次使用"角标）
        导出结果 Card：
          成功：包名 + 大小 + 引擎 Badge + 文件树（等宽 12px，目录域色）+ 校验 Checklist + 下载主 CTA
          失败：danger 顶部条 + 原因 + 重试
右 4列：资产摘要 Card（KV）
        运行时校验 Card（校验项 + score + 阈值）
        导出历史 Card（时间线，可重新下载）
```

**交互**：导出中 CTA loading（不改变容器高度）；成功后自动展开结果并 Toast；下载触发浏览器原生下载；历史项 hover 显示重新下载与复制路径。

**响应式**：<1280 右栏落底两列；<768 单列，下载按钮吸底全宽。

---

## 8. 技术中心 Technology Center（/technology） — 品牌页

**目标**：以品牌叙事解释三项自研引擎，补齐当前"10 行裸页面"的短板。

**布局**
```
Hero：display-xl「把创意锻造成可运行的资产」+ 渐变字标 + 副标 + CTA（生成资产 / 查看基准）
核心引擎（3 列，域色）：PReCon / FAlign / GImport
  └ 大号图标块 + 名称 + 中英说明 + 3 个指标 KV + "查看基准数据 →"
流程长图：Generation → PReCon → FAlign → GImport → QA → Engine，横向 Stepper 带域色
架构说明（2 列）：资产协议 CreativeAsset v1.0 / 多智能体协作
页脚：版本、仓库、许可证
```

**响应式**：Hero `display-xl`→`h1`；引擎卡 3→1 列；流程长图横向滚动。

---

## 9. 全局状态与文案规范

| 场景 | 规范 |
|------|------|
| 加载 | Skeleton 优先；超过 800ms 显示文案「正在运行真实管线…」 |
| 空状态 | 一句价值说明 + 一个主 CTA，不出现"暂无数据"裸文案 |
| 失败 | 原因 + 影响 + 两个动作（重试 / 返回），禁止只显示 error 对象 |
| 成功 | Toast + 就地结果，不用 `alert` |
| 文案 | 中文主 + 英文 `overline` 副；术语表：任务图 / 检查点 / 修复轮 / 相位对齐 / 根运动纠偏 |
| 数字 | 百分比整数、像素保留 2 位、时间 `mm:ss`，全部 tabular |
| 按钮 | 动词开头：「生成资产」「导出工程包」「重新运行」，禁止「确定/提交」 |
