# 04 · 动态内容区设计规范 — 实况流（LiveStream）

> 适用范围：`studio/frontend` 实时事件型动态内容区域。
> 参考实现：`src/components/live/LiveStream.tsx`（容器）+ `src/hooks/useTaskFeed.ts`（数据规整）+ `src/hooks/useVirtualWindow.ts`（虚拟滚动）+ `src/lib/motionPresets.ts`（动效参数层）。
> 色彩/字体/组件基线沿用 `02-visual-spec.md`，本文只约束动态内容区的行为、状态与性能。

---

## 1. 定位与场景

实况流是「随时间增长的实时列表」的统一容器：任务事件流（AgentDashboard 事件流）、后续可复用于批量生产进度、展示间发布日志等。它解决的问题：

- 事件持续追加 → 内存与 DOM 必须有界（缓冲裁剪 + 虚拟滚动）；
- 用户需要按交互重组内容（分类筛选、关键词搜索）；
- 实时性要求内容插入可感知但不喧宾夺主（轻进场动画 + 可感知的状态反馈）；
- 网络/后端不稳定 → 连接降级与中断必须有区分的呈现（非致命提示 vs 致命错误）。

## 2. 交互与状态响应

| 交互 | 响应 | 反馈 |
| --- | --- | --- |
| 点击分类 chip（全部/调度/生成/引擎/质量/系统） | 即时过滤列表 | 激活 chip 实底高亮；计数条更新「显示 X / Y 条」 |
| 输入搜索词（事件/智能体/详情全文匹配，大小写不敏感） | 即时过滤 | 同上；无匹配时空态给出「清除筛选」出口 |
| 点击「重新连接」 | 断开并重建 WebSocket→轮询链路 | 重连代数 +1，效果为事件恢复流入 |
| 新事件到达 | 追加到列表尾 | 普通模式逐行滑入动画；贴底跟随（用户在底部附近才自动滚动，向上翻阅不打扰） |
| 内容切换（筛选变化） | 列表重排 | 滚动位置归零，保证切换可感知 |

读屏支持：普通模式列表 `role="log" aria-live="polite"`；虚拟模式改为计数条静态播报（避免滚动噪音）。

## 3. 状态矩阵（必须四种齐备）

| 状态 | 呈现 | 实现 |
| --- | --- | --- |
| 加载中 | 骨架行 ×9，行高与成品一致 | `SkeletonRows`（零 CLS） |
| 加载失败（致命） | `ErrorState`：警示图标 + 描述 + 重新连接按钮 | `ui.tsx` ErrorState |
| 空数据 | `EmptyState`：图标 + 标题 + 指引 + 行动按钮 | 复用 ui.tsx |
| 筛选无匹配 | 空态复用：说明原因 + 「清除筛选」 | 同上 |
| 连接降级（非致命） | 黄色警示条横幅，不阻断内容 | `notice` prop + StatusDot warning |

## 4. 动效参数（lib/motionPresets.ts）

时长一律引用 `lib/motion.ts` 令牌（fast 120ms / base 180ms / slow 260ms），禁止裸写 ms。

| 预设 | 用途 | 参数 |
| --- | --- | --- |
| `SLIDE_IN` | 事件行插入/移除 | opacity 0→1 + x -8→0，120ms，`EASE_STANDARD` |
| `FADE_RISE` | 块级内容插入 | opacity + y 10→0，180ms |
| `CONTENT_SWAP` | 视图/Tab 内容切换 | opacity + y 6→0，120ms |
| `SPRING_SOFT` | 位置弹动（layout） | stiffness 170 / damping 28（无过冲区间） |
| `STAGGER_PARENT/ITEM` | 列表交错进场 | staggerChildren 120ms |

触发条件约定：普通模式（≤virtualThreshold）逐行动画由 `AnimatePresence` 挂载/卸载触发；虚拟模式放弃逐行退场动画（滚动重挂载会重放，闪烁），只保留 header 状态点脉冲。系统 `prefers-reduced-motion` 声明降级时，`useMotionPref().pick()` 返回零时长版本，组件零改动。

## 5. 性能策略

1. **有界数据**：`trimBuffer` 把内存日志截到 400 条（超出丢最旧），老事件归档到历史页。
2. **虚拟滚动**：`useVirtualWindow` 零依赖实现——定高行 + rAF 节流 scroll + passive 监听 + ResizeObserver 跟随容器高度；`overscan=6` 防滚动露白。行数 ≤80（`staticBreakEven` 附近，默认阈值 80）自动降级普通列表以保留进出场动画。
3. **渲染收敛**：行组件 `memo`；筛选/搜索/规整全部 `useMemo`；滚动窗口只在 range 变化时 setState。
4. **零 CLS**：定高行（默认 40px）+ 骨架行高一致 + 总高占位（`count × rowHeight`）撑出真实滚动条。
5. **GPU 友好**：动画只动 `transform/opacity`；虚拟行用 `position:absolute + top` 定位（不触发布局链）。

实测数据见 `docs/perf/dynamic-content-perf-20261006.md`：400 条事件 @10ms 灌入，虚拟开 0 长任务/平均帧 6.1ms，虚拟关 80 长任务/最差帧 121ms。

## 6. 组件 API

```tsx
<LiveStream
  items={StreamItem[]}          // useTaskFeed(events) 产出
  loading? error? onRetry?      // 加载/致命错误
  notice?                       // 非致命提示（连接降级）
  emptyTitle? emptyDescription? emptyAction?
  height?={430} rowHeight?={40}
  virtualThreshold?={80}        // Infinity 强制普通列表
/>
```

数据侧：`useTaskFeed(events, buffer=400)` → `{ items, counts }`；纯函数 `normalizeTaskEvents / trimBuffer / filterStreamItems / countByKind` 均可单测。复用方式：任何「实时追加列表」传不同 `items` 与空态文案即可，无需改动容器。

## 7. 浏览器兼容

- 依赖特性：`ResizeObserver`（缺失时退化为仅滚动驱动，功能不损失）、`PerformanceObserver`（仅基准测量用，运行时零依赖）。
- Chrome/Edge ≥ 88、Firefox ≥ 103、Safari ≥ 15 全功能；旧浏览器虚拟滚动退化为普通滚动行为。
- jsdom/测试环境：无布局引擎时渲染首窗（overscan 窗口），测试用 `scrollTop + dispatchEvent('scroll')` 驱动。

## 8. 已知取舍

- 虚拟模式无逐行退场动画（AnimatePresence 与绝对定位窗口不兼容）——换取 400 条流量下零长任务。
- 定高行设计：事件详情超长时截断（title 悬停看全文），不支持行内展开。展开需求出现时应改用「点击弹层」而非破坏定高。
- 缓冲 400 条为实测校准值：覆盖一次完整五段管线的全部事件（实测单任务峰值 ~120 条）并留 3 倍余量。
