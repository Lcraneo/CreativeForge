# 动态内容区性能测试报告 — LiveStream 实况流

- 日期：2026-10-06
- 环境：Windows 10 x64 · Chrome（ZCode 内嵌 Chromium）· Vite dev 模式 · 1600×1000 视口
- 被测对象：`AgentDashboard` 执行记录面板 → `LiveStream`（智能体指挥中心事件流）
- 负载模型：模拟实时任务事件流，**400 条事件按 10ms 间隔灌入 zustand store**（6 类事件循环，含 agent/detail 字段），模拟高频追加的真实管线
- 测量方式（页面内 PerformanceObserver + rAF 采样）：
  - `longtask`：>50ms 主线程长任务计数
  - `requestAnimationFrame` 帧间隔：均值 / P95 / 最差
  - `layout-shift`（无输入累计）：CLS
  - DOM 行数（虚拟窗口实际渲染行）、`performance.memory` 堆用量

## 1. 结果对比

同一负载（400 条 @10ms），同一页面，唯一变量为 `localStorage["cf-live-virtual"]` 强制模式（仅 dev 生效的基准开关）：

| 指标 | 虚拟滚动开（≥80 行自动启用） | 虚拟滚动关（全量列表+逐行动画） |
| --- | --- | --- |
| 长任务数（>50ms） | **0** | **80** |
| 最差长任务 | — | 78ms |
| 平均帧间隔 | **6.1ms** | 54.5ms（灌入中段）→ 18.3ms（全程均值） |
| P95 帧间隔 | **18ms** | 97ms |
| 最差帧间隔 | **30.3ms** | 121.1ms |
| CLS（无输入） | 0.0054 | 0.0054 |
| DOM 事件行 | **21**（仅渲染窗口） | 400（全量挂载） |
| 堆内存（灌入中） | **17MB** | 69MB（GC 后回落 17MB） |
| 400 条总耗时 | **≈5.2s**（贴近注入目标 4s） | **22.0s**（被渲染拖慢 5.5 倍） |

两组 CLS 均为 0.0054——唯一一次布局漂移来自「连接中断提示」横幅插入（预期内、一次性）；骨架行高与成品行高一致，内容替换零漂移。

## 2. 结论

1. **虚拟滚动是本场景的硬要求而非优化项**：400 条全量渲染时主线程被 framer-motion 逐行 layout 动画打满（1/3 以上帧超 50ms），而虚拟模式全程零长任务、帧间隔稳定在 60fps 线内。
2. **默认阈值 80 行合理**：80 行以下普通模式的进出场动画开销可忽略（30 条用例帧间隔与虚拟模式无可测差异），保留动画收益；超过即自动切换。
3. **内存有界**：缓冲裁剪 400 条 + 仅渲染窗口行，堆增量 <5MB；关闭虚拟时灌入中堆峰值 69MB（全量 DOM + 动画实例）。
4. **CLS 达标**（<0.01，"good" 阈值 0.1）。

## 3. 回归门禁

- vitest：15 个文件 78 用例全绿（含虚拟窗口滑动/收缩钳制、LiveStream 筛选/搜索/空/错态/虚拟化 6 组交互用例）
- `tsc -b && vite build`：通过
- 基准可复现：`localStorage.setItem("cf-live-virtual","on"|"off")` → 刷新 `/agents` → 控制台跑 `window.__cf` 注入脚本（仅 dev 构建暴露）

## 4. 附：测量脚本要点

页面内注入（通过 `window.__cf.useAgentStore`，`import.meta.env.DEV` 门控）：

- 采样 rAF 帧间隔数组 → 排序取 P50/P95/Max
- `PerformanceObserver({entryTypes:["longtask"|"layout-shift"]})`
- 结果对象挂 `window.__bench`，外部轮询读取（避免单次 evaluate 超时）

局限：dev 模式（React development build + 未压缩）测量，生产构建绝对值会更低；两组对照在同一构建下进行，**结论（虚拟开 vs 关的相对差）不受影响**。
