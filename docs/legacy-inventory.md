# 遗留系统处置看板（Q4 4.2）

> 冻结 → 迁移 → 删除 三里程碑。创建于 2026-09-30，删除完成后归档本文件。

## 现状快照

| 项 | 遗留 backend/ | 遗留 frontend/ | 活跃 studio/ |
|---|---|---|---|
| 体量 | 179 个 py（git 跟踪） | MVP 三页 | ~30 py 后端 + 40 前端文件 |
| 来源 | Phase 11-23 旧后端 | Phase 21 MVP | 当前主线 |
| CI | 不运行 | 不运行 | 全部门禁 |
| lint | 已排除（pyproject extend-exclude） | — | 全量受管 |
| 被活跃代码依赖 | **零**（architecture 冻结测试固化） | **零** | — |

遗留 backend/ 结构：`app/engines` 81、`app/runtime` 26、`tools` 12、`models` 10、
`api` 10、`adapters` 9、`schemas` 7、`services` 7、`core` 3、`agent` 3、测试 8。

## 里程碑

### M1 冻结 ✅ 2026-09-30
- 架构测试 `run_tests.py::architecture`：活跃目录出现 `import backend/frontend` 即 FAIL。
- pyproject lint 排除遗留目录；CI 不跑遗留测试（本来就只跑 tests/ 与 studio）。

### M2 迁移（按需，触发式）
原则：**不做大迁移**。只有当某个功能要"复活"时，才把对应模块按 CreativeAsset
协议重写进 studio/（Q1-Q3 已证明 studio 服务层 + agent 层覆盖主线需求）。
候选复查点（如需复活时逐个评估）：
- `app/engines/`（81 py）：与 artgen/ 三引擎 + adapters/ 引擎适配重叠度待逐个比对
- `app/api/`：studio/backend/api/routes.py 已覆盖当前全部前端调用（client.ts 60 端点）
- `models/` + `schemas/`：pydantic 模型，studio 以 pydantic + types.ts 双端契约替代

### M3 删除（需要显式决定）
前提 checklist：
- [ ] M2 复查完成，确认无独占功能（尤其 `app/engines/` 与 `tools/`）
- [ ] `git ls-files backend/ frontend/` 清单归档（本文件即记录起点）
- [ ] `git rm -r backend frontend` + pyproject 移除排除项 + 本文件归档
预期收益：仓库 py 体量减半（333 → ~154），clone/索引/lint 提速。

## 度量

| 日期 | 遗留 py 数 | 活跃代码对遗留依赖数 |
|---|---|---|
| 2026-09-30 | 179 | 0（冻结测试守护） |
