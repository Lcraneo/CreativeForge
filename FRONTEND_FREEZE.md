# FRONTEND_FREEZE — 旧前端冻结说明（已终结：2026-10-05 删除完成）

> **状态更新**：本文所述的"先冻结，后删除"流程已走完——`frontend/`（MVP 三页）与
> `backend/`（旧 MVP 后端）已于 2026-10-05 整体删除，处置记录见
> `docs/legacy-inventory.md`。下文保留为历史决策记录。

本仓库存在两套 Web 产品：

| 目录 | 定位 | 状态 |
| --- | --- | --- |
| `studio/frontend` | **CreativeForge Studio 唯一正式 Web 产品** | ✅ 继续开发 |
| `frontend/` | 早期 MVP 三页产品（Phase 21，直连 `backend/`） | 🧊 **冻结**（不再新增功能） |

## 为什么只保留 Studio

CreativeForge 的产品形态是「自然语言目标 → Agent 动态规划 → Live Canvas 实时产出 →
资产/动画/导出」，这条主线由 `studio/`（前端 + 后端 + Agent Runtime）承载。旧的
`frontend/` 是固定三页流程，与主线不一致。

## 冻结策略（先冻结，后删除）

1. `frontend/` 停止新增功能与结构性改动。
2. `studio/` 成为唯一正式入口（默认路由 `/` = 创作工作台 `CreativeStudio`）。
3. 待 `studio` 的功能完全覆盖旧 `frontend/`（创建 / 时间线 / 资产 / 导出）后，再物理删除
   `frontend/` 与 `backend/`（旧 MVP 后端）。

在此之前不删除，避免误删仍被脚本/类型引用的旧接口。

## 迁移状态

- 创建 / 自然语言入口 → `studio/frontend` `CreativeStudio` + `Workspace`
- 任务时间线 / Agent 事件流 → `studio/frontend` `AgentDashboard` + WebSocket
- 资产检查 / 三视图 / 动画 / 导出 → `studio/frontend` `AssetInspector` / `DesignCenter` /
  `AnimationStudio` / `ExportCenter`
- 图像生成内核 → 共享 `artgen`（两套前端都用），后续统一由 `studio` 调用

旧 `frontend/`、`backend/` 保留仅供回归参考，不再是正式产品面。
