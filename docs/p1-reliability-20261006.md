# Studio P1 可靠交付：任务持久化 / 基准后台刷新 / 幂等键 / 超时分级 / 移动端抽屉

日期：2026-10-06。承接 2026-10-05 的 P0 与资产上下文批次（见
`frontend-p0-20261005.md` / `frontend-p1-asset-context-20261005.md` /
`frontend-p2-3d-chunk-20261005.md`），本批完成其「后续顺序」中的可编码项。

## 改动

### 1. 动画生成任务落盘（后端）

- 新增 `studio/backend/animation_service/task_store.py`：视频生成任务
  （`_VIDEO_TASKS`）与动作批次（`_ACTION_BATCHES`）快照原子落盘到
  `studio/backend/data/animation_tasks.json`（同 `persistence.py` 的
  tmp + .bak + replace 约定）；每次状态迁移后覆盖写，只存任务描述字段，
  不含源图字节。
- 进程启动时 `restore()` 读回快照：仍处于 running 的任务线程已随旧进程
  消亡——标记为 **interrupted（终态）**，前端不再无限轮询或静默 404；
  超过 TTL 的历史条目直接丢弃。
- 不承诺恢复执行（i2v 输入未持久化），中断即语义终点；已完成任务保留
  结果快照，刷新后仍可直接取回结果。
- 队列中心动作批次新增「已中断」徽章；快照类型补 `interrupted` 状态。

### 2. 基准手动刷新转后台（后端 + 前端）

- `BenchmarkCache.get(refresh=True)` 不再同步阻塞约 13 秒：立即返回现有
  报告（附 `cache: {cached_at, refreshing}` 元数据），真实评测转后台线程，
  重复点击合并为一次；失败保留旧报告。冷启动（无缓存）保持同步评测。
- 过期普通读撞上后台刷新时直接返回旧报告，避免重复计算。
- 基准中心：`refreshing` 期间按钮显示「后台评测中…」、顶部提示当前展示
  的报告时间，报告查询每 4s 轮询至完成后自动更新。

### 3. 生成幂等键：防重复扣费（后端 + 前端）

- 新增 `studio/backend/idempotency.py`（同键 TTL 窗口内复用首个结果）。
- `POST /api/animation/tasks` 接受 `Idempotency-Key` 请求头：同键且已存
  任务仍在运行 → 返回已存快照，不重复入队、不重复扣费；任务已终结
  （done/failed）→ 放行重新生成。无键行为不变。
- 前端 `AnimationStudio` 每次用户提交生成 `crypto.randomUUID()` 作为键。

### 4. 请求超时分级（前端）

- `request()` 支持 `timeoutMs`：与调用方 `AbortSignal` 组合（手动桥接，
  不依赖 `AbortSignal.any`），超时转 408 `ApiError`。
- 分级接入：任务详情 10s；资产/任务/矩阵/批次/骨架检查等读接口 15s；
  基准报告 120s（冷启动真实评测 10s+）；手动刷新 30s。长任务创建与
  同步生成端点不设超时，保持原语义。

### 5. 窄屏参数抽屉（前端，动画工作台）

- <1280px 时右侧参数/模型面板转为右侧抽屉：同一容器 `max-xl:fixed` 位移
  切换（无 JSX 复制、无双份渲染），遮罩点击/Esc 关闭、锁定背景滚动；
  ≥1280px 恒为静态侧栏。动效走 `--motion-base` 令牌（架构边界测试约束）。
- 移动端导航已在上一批交付（`MobileNavigation`），本批补齐参数可达性。

### 6. MP4 交付核验（路线图修正项，无代码变更）

路线图「新增 MP4」按实际代码核验为**已交付**，证据：

- 后端 `_deliver_video_mp4()`：i2v 源视频按抽帧窗精确裁剪，原速原分辨率
  直通交付（H.264 CRF16 + faststart），纯增益路径（失败降级返回 None，
  GIF 不受影响）；meta `urls.video` 暴露 `/api/animation/{id}.mp4`。
- 前端：结果区 `<video>` 播放 + MP4 下载入口 + 规格（宽高/帧率）展示；
  「AI 视频驱动」开关即格式选择。
- 导出：角色包 `engine_tag` 含 `video → ai-video`，视频型动画随包交付。
- 批次补齐走试玩条带（`with_mp4=False`）为省时有意设计，非遗漏。

## 验证记录

- 后端单测 23/23：缓存后台刷新语义重写（立即返回旧报告/合并/失败保留/
  过期读避让）+ 新增 task_store（中断标记/终态保留/TTL 丢弃/损坏容错）、
  idempotency（TTL/空键）、幂等路由（运行中复用/终态放行/无键不变）。
- 契约检查 45/45（`tests/run_tests.py`）。
- 前端：TypeScript 通过；Vitest 62/62（含架构边界——抽屉动效令牌已按
  约束改用 `--motion-base`）；生产构建通过。
- 8600 实机冒烟（httpx，种子任务 → 启动 → 验证）：
  - 伪造 running 任务/批次重启后：任务与批次均返回 `interrupted`（终态）；
  - 基准冷启动 13.6s（真实评测，一次性）→ 热读 **3ms**；手动刷新
    **62ms** 返回旧报告 + `refreshing=true`（旧实现阻塞约 13s）；
  - `POST /api/animation/tasks` 无资产 → 409（路由链路正常）。
- 冒烟种子数据已清理；`studio/backend/data/` 在 .gitignore 内。

## 边界与遗留

- **一个目标引擎的真实导入闭环**：需要在真实 Unity/Cocos/Godot 编辑器中
  加载资源并播放动画（技术验证依赖编辑器环境），本批未实施；当前导出页
  已如实区分「包结构校验」与「编辑器实际导入验证」（上一批交付）。
- 大图分级解码、资产检查器重 chunk 进一步拆分：归入后续性能批次。
- 任务落盘为单进程 JSON 方案；多进程/分布式部署需要外移到数据库。
