# Contributing to CreativeForge

质量约定速查——完整质量体系见 `quality-plan.md`，评分历史见 `docs/quality-scores.md`。

## 质量门（全部绿才可合并/发布）

| 门 | 命令 | 内容 |
|---|---|---|
| L1-L5 发布门 | `python tests/release/run_release_tests.py` | 契约 / 管线 / 运行时 / 性能预算 / 前端（体积+vitest+lint+tsc） |
| 单元与契约 | `python tests/run_tests.py` | 39 项：falign / gimport / agent / multi-agent / architecture |
| Studio API | `python studio/backend/tests/*.py` | 动态规划 API、guest 演示试玩 |
| 前端 | `npm run lint && npm run typecheck && npm run test` | eslint / tsc / vitest（含 boundaries 架构测试） |

CI（GitHub Actions）双工作流必绿；gitleaks 扫描密钥。

## 提交约定

1. **功能必附测试**。新增能力/修复 bug 都要在 `tests/run_tests.py`、studio API 测试或
   vitest 里留下断言——竞品每一模块带测试的文化，我们照做。
2. **决策写进代码旁**。为什么这样做、放弃了什么，用注释说清楚（中文注释是本仓库惯例）。
3. **动效走令牌**。CSS 用 `index.css @theme` 的 `--motion-*`，framer 用 `lib/motion.ts`
   的 `MOTION`——组件里禁止裸写时长（boundaries 测试会拦）。
4. **边界不可破**。pages 不直接 import three；裸 fetch 只在 `api/client.ts`；
   活跃代码不 import 遗留系统（`backend/`、`frontend/` 已于 2026-10-05 删除，门禁保留防回归）。
5. **密钥不落盘不入库**。API key 走 `.env` / 环境变量（后端 `STUDIO_AUTH_TOKEN`、
   模型 key 等）；`model_settings.json` 已 gitignore，别再把它加回来。

## 本地环境备忘

- node 在 `C:\Tool\node.exe`（不在 PATH），tsc 用
  `C:\Tool\node.exe node_modules\typescript\bin\tsc -b`。
- vitest 锁 v3（vite 5 兼容）；升级 vite 前不要动它。
- 遗留 `backend/`、`frontend/` 已删除——见 `docs/legacy-inventory.md`；需要旧功能时
  从 git 历史找回对应模块，按 CreativeAsset 协议重写进 `studio/`，不要直接复活。
