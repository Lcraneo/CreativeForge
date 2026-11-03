# CreativeForge 贡献指南

提交前先阅读 `README.md` 和 `ARCHITECTURE.md`。新增功能应同时补充可执行测试，
涉及架构边界或数据流的改动应同步更新 `ARCHITECTURE.md`。

## 质量门（全部绿才可合并/发布）

| 门 | 命令 | 内容 |
|---|---|---|
| L1-L5 发布门 | `python tests/release/run_release_tests.py` | 契约 / 管线 / 运行时 / 性能预算 / 前端（体积+vitest+lint+tsc） |
| 单元与契约 | `python tests/run_tests.py` | falign / gimport / agent / multi-agent / architecture |
| Studio API | `python -m unittest discover -s studio/backend/tests -p "test_*.py"` | 后端 API、服务和运行时 |
| 前端 | `npm run lint && npm run typecheck && npm run test` | eslint / tsc / vitest（含 boundaries 架构测试） |

CI（GitHub Actions）双工作流必绿；gitleaks 扫描密钥。

## 提交约定

1. **功能必附测试**。新增能力/修复 bug 都要在 `tests/run_tests.py`、studio API 测试或
   vitest 里留下断言——竞品每一模块带测试的文化，我们照做。
2. **决策写进代码旁**。为什么这样做、放弃了什么，用注释说清楚（中文注释是本仓库惯例）。
3. **动效走令牌**。CSS 用 `index.css @theme` 的 `--motion-*`，framer 用 `lib/motion.ts`
   的 `MOTION`——组件里禁止裸写时长（boundaries 测试会拦）。
4. **边界不可破**。pages 不直接 import three；裸 fetch 只在 `api/client.ts`；
   活跃代码不 import 已删除的遗留系统。
5. **密钥不落盘不入库**。API key 走 `.env` / 环境变量（后端 `STUDIO_AUTH_TOKEN`、
   模型 key 等）；`model_settings.json` 已 gitignore，别再把它加回来。

## 本地环境备忘

- ESLint 10 要求 Node.js `20.19+`、`22.13+` 或 `24+`；使用旧版 Node 时
  `npm test` 能运行，但 `npm run lint` 会在 ESLint 启动阶段失败。
- vitest 锁 v3（vite 5 兼容）；升级 vite 前不要动它。
- jsdom 锁 v26（本地 Node 18.19 兼容）。jsdom ≥30 要求
  `node ^22.22.2 || ^24.15.0 || >=26`，在 Node 18 下 vitest 环境会全部
  报错；升级 Node ≥22.22 后可还原 `jsdom@^30`。
- 遗留 `backend/`、`frontend/` 已删除；需要旧功能时从 Git 历史找回对应模块，
  按 CreativeAsset 协议重写进 `studio/`，不要直接复活。
