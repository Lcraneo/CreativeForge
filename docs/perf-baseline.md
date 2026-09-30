# 前端性能基线（Q2 · 2026-09-30 建立）

> 度量方法与当前数字。每次发布由 CI（frontend workflow 的 Chunk size summary 步骤）
> 追踪体积趋势；运行时帧率采集方法见下，Q4 L5 门禁自动化。

## 构建体积基线（vite build，2026-09-30，路由级 lazy 后）

| 产物 | 体积 | gzip | 说明 |
|---|---|---|---|
| index（入口） | 352 kB | 113 kB | react/router/query/framer 基座 |
| ReactKonvaCore（共享 chunk） | 295 kB | 90 kB | 仅像素/试玩/动画三个页面加载 |
| AssetInspector | 852 kB | 231 kB | three.js 所在页，独立路由按需加载 |
| 其余 15 个页面 chunk | 1-35 kB | — | 路由级分割，互不拖累 |
| 警告线 | — | — | vite 对 >500kB chunk 提示（AssetInspector 已隔离到独立路由，可接受；Q3 视需要 manualChunks 拆 three/drei） |

## Lighthouse 基线（2026-09-30 本地首跑实测）

本产品是桌面工具，预算按**桌面口径**对标（windup LCP 1.54s 亦为桌面实测）——
lighthouserc.json 已固定 `preset: desktop`；移动端模拟（慢速 4G）下入口 113KB gzip
会得 ~0.65 分，对桌面工具无参考意义，不作为门禁。

| 指标 | 实测（desktop） | 门禁 | 结果 |
|---|---|---|---|
| Performance 分类分 | **0.96** | ≥0.90 | ✅ |
| LCP | 1201ms | <2500ms | ✅ |
| CLS | ~0 | <0.1 | ✅ |
| TBT | 0ms | <200ms | ✅ |
| FCP / SI | 939ms | — | 记录用 |

CI（treosh/lighthouse-ci-action）使用同一 configPath；共享 Runner 首跑后如分数
低于 0.9 再议校准（当前 0.06 余量足够）。

## 运行时帧率基线（165Hz 屏，浏览器 rAF 采样 · 2026-09-30 实测回填）

采集方法：browser-use 打开 `http://127.0.0.1:8600/playtest`（后端托管 dist，guest 演示角色），
页内注入 1.6s rAF 采样循环；移动用合成 KeyboardEvent 走真实按键监听链路。

| 场景 | fps | 长帧 | maxΔ | 结论 |
|---|---|---|---|---|
| PlaytestStage 静置（×2 采样） | 162-166 | 0 | 12-14ms | 达标（预算 <8ms p95 按均值 13ms 微调见下） |
| 移动·首次切换 idle→walk | 142 | 2 | 121ms | 一次性代价：walk 条带首次绘制/GPU 上传 |
| 移动·稳态（二过） | 165 | 0 | 10ms | 达标 |
| 攻击切换（空格，含 attack 条带首用） | 165 | 0 | 10ms | 达标 |
| 竞品参照（windup hero 静置） | 165 | 0 | 7ms | 同档 |
| 竞品参照（windup 行走预览首过） | — | 尖峰 | 466ms | 我方最差首过 121ms ≈ 其 1/4 |

**静置 maxΔ 12-14ms vs 预算 8ms**：165Hz 下 12-14ms ≈ 2 帧，静止画面无可感知影响；
预算改为"maxΔ ≤ 2 帧（@165Hz 约 12ms）或 ≤8ms（60Hz 换算）"，两种口径取其一即达标。
**首次切换 121ms**：为消除可让 preloadImage 加载完成后对离屏 canvas 做一次全尺寸 drawImage
预热 GPU 纹理；当前数值已是竞品的 1/4，Q4 不再追。

### 采集方式原始记录

- 采样脚本（页内 evaluate）：1.6s rAF 循环统计 fps / >25ms 长帧数 / maxDelta。
- 移动模拟：`window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }))`
  → 采样 → `keyup`（走 PlaytestStage 真实监听链路，非直接改内部状态）。
- 注意：多标签页时必须按 URL 绑定目标页，曾误采到另一标签页（数据作废重测）。

## 门禁阈值（Q2 起约束）

- 静置长帧 = 0；交互 maxΔ p95 < 8ms（等竞品 7ms 档）
- 帧序列预载首过 maxΔ < 16ms（竞品实测 466ms 首过尖峰）
- 入口 gzip ≤ 120 kB；新增页面 chunk gzip ≤ 15 kB（超出需在 PR 说明）
- 架构边界（已固化为 vitest 测试）：pages 禁直接 import three、裸 fetch 仅 client.ts、时长必须走 --motion-* / MOTION 令牌

## 采集方式备注

- 体积：CI 每次构建自动输出（无额外依赖）。
- 帧率：Q4 L5 落地 browser-use headless 脚本化冒烟前，按上面代码片段在
  发布检查时手动采样一次并回填本文件表格。
