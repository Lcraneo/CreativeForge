# Phase 设计规范归档（CreativeForge）

CreativeForge 的 23 个 Phase 设计/决策记录：Phase 1-10 描述项目从早期设计命名（AssetStruct / CharacterDNA / MotionAlign / GameAssetCompiler）演进为最终自研技术链（PReCon / FAlign / GImport）的完整设计旅程；Phase 11-15 是真实后端的实现框架（FastAPI + PostgreSQL + 引擎接入）；Phase 16-19 将后端从"手动调用工具"升级为"Agent 自主生产系统"（编排 / Runtime / 产品化 / 模型层）；Phase 20 打通模型训练与部署工程（数据集 → 对比训练 → 模型注册表 → 模型服务 → GPU 分层）；Phase 21 落地 MVP 前端（Creation Studio / Agent Timeline / Asset Viewer）与 zip 导出闭环；Phase 22 升级为自主决策型 Agent 平台（动态 Planner 短链路 / 置信度自评估 / MCP 工具生态 / 多人协作 + 多租户）；Phase 23 补齐研究创新层（知识图谱 + RAG / Game Logic Agent / Simulation Agent / 任务级 Evaluation / Game Creation Benchmark），均已按框架补全并合并到 `backend/` 与 `frontend/`。

> 这些 Phase 文档是设计决策记录，保留原始设计意图与演进路径；最终实现以 [docs/architecture.md](../architecture.md) 架构文档为准。

## 总览

| Phase | 标题 | 核心问题 | 最终合并位置 |
| ----- | ---- | -------- | ------------ |
| [1](phase1.md) | CreativeAsset v2 契约 | 任何输入归一为 CreativeAsset | `schemas/` + `packages/creative-core/` + `core/` |
| [2](phase2.md) | Windup Adapter v2 | 外部生成能力统一接入 | `adapters/` + `core/registry.py` + `docs/mapping/` |
| [3](phase3.md) | AssetStruct Engine | AI 图片 → 游戏资产结构 | `precon/`（PReCon） |
| [4](phase4.md) | Character DNA Engine | 角色跨动作身份一致性 | `precon/style/` + `agent/memory` + `agents/memory_agent/` |
| [5](phase5.md) | MotionAlign Engine | AI 动画 → 游戏动画 | `falign/`（FAlign） |
| [6](phase6.md) | GameAsset Compiler | CreativeAsset → 游戏资源包 | `gimport/{atlas,animation,prefab,manifest}` |
| [7](phase7.md) | GImport Engine | 资源包 → 引擎工程 | `gimport/{adapters,validation,exporter}` |
| [8](phase8.md) | Agent + Workspace + Benchmark | 自主规划型生产 Agent | `agent/` + `agents/` + `studio/`（benchmark 独立为 Phase 9） |
| [9](phase9.md) | MVP 工程落地 | 最小实现验证核心价值 | `benchmark/` + 最终 8 层架构 |
| [10](phase10.md) | 技术选型 + 仓库结构 | 最终技术路线与结构 | 最终 8 层 + `studio/` + `examples/competition_demo` + `tests/release` + `docker` |
| [11](phase11.md) | Backend 第一版实现 | 真实可扩展的服务骨架 | `backend/`（app/core + models + agent + tools + services + api） |
| [12](phase12.md) | 真实 AI 能力接入层 | 外部 AI → Adapter → CreativeAsset | `backend/app/adapters/`（base / windup / holonic / registry） |
| [13](phase13.md) | AssetStruct Engine 深度实现 | AI 图片 → 可编辑游戏资产结构 | `backend/app/engines/asset_struct/` + `backend/app/models/asset_struct.py` |
| [14](phase14.md) | Character DNA Engine 深度设计 | 角色身份一致性 + 版本演进 | `backend/app/engines/character_dna/` + `backend/app/models/character_dna.py` + `backend/app/api/dna.py` |
| [15](phase15.md) | MotionAlign Engine（重新规划版） | AI 动画 → 游戏行为 + 引擎导入 + 碰撞体 | `backend/app/engines/motion_align/` + `backend/app/engines/gimport/` + `backend/app/models/animation.py` |
| [16](phase16.md) | Agent Orchestration Layer | 用户只描述目标，Agent 自主决定模块与顺序 | `backend/app/runtime/`（intent / planner / graph / agents / registry / quality） |
| [17](phase17.md) | Agent Runtime（生产级） | 状态机 + 断点续跑 + 三层记忆 + 自愈 + 审核 | `backend/app/runtime/`（executor / gateway / memory / versions / review / healing）+ `app/models/runtime.py` |
| [18](phase18.md) | Product Layer | 不需要理解引擎模块，一句话完成生产 | `backend/app/api/`（轨迹 / approve / export）+ schemas |
| [19](phase19.md) | Foundation Layer（模型层设计） | 六层 DNA / 资产图谱 / 动画理解 / 一致性评估 | `backend/app/engines/foundation/`（dna_profiles / quality_model / animation_library） |
| [20](phase20.md) | Model Training & Deployment（模型训练与部署工程） | 自研边界 / 身份数据集 / 对比训练 / 模型注册表 / GPU 分层 | `backend/app/engines/foundation/training/` + `backend/app/models/training.py` + `backend/app/api/models.py` + `backend/app/runtime/tiers.py` |
| [21](phase21.md) | MVP Engineering Plan（工程落地版） | 一句话 → 资产 → Cocos 的最小闭环 + 三页面前端 | `frontend/`（Studio / Timeline / Viewer）+ `backend/app/api/asset.py`（export.zip）+ `backend/app/services/export_service.py` |
| [22](phase22.md) | Advanced Agent Platform（高级 Agent 平台） | 动态 Planner / 置信度自评估 / MCP 工具生态 / 协作与多租户 | `backend/app/runtime/`（planner/evaluation/style 链路）+ `backend/app/api/mcp.py` + `backend/app/api/collab.py` + `backend/app/models/collab.py` |
| [23](phase23.md) | Research & Innovation Layer（研究创新层） | 知识图谱 + RAG / Game Logic / Simulation Agent / Game Creation Benchmark | `backend/app/engines/foundation/{knowledge,game_logic,simulation,benchmark}.py` + `backend/app/api/{knowledge,benchmark}.py` + `backend/app/runtime/agents/{logic,simulate}.py` |

## 设计旅程（命名演进）

```text
Phase 设计命名                              最终实现命名
---------------------------------          ----------------------
CreativeAsset Contract v2        ───►      CreativeAsset v1.0 冻结契约
Windup Adapter v2                ───►      adapters/（能力接入层）
AssetStruct Engine               ───►      PReCon 像素重建引擎
Character DNA Engine             ───►      precon/style + agent/memory
MotionAlign Engine               ───►      FAlign 切帧对齐引擎
GameAsset Compiler               ───►      gimport/{atlas,animation,prefab,manifest}
GImport Engine                   ───►      gimport/{adapters,validation,exporter}
Agent + Workspace                ───►      agent/ + agents/ + studio/
Benchmark                        ───►      benchmark/
技术选型 + 仓库结构                ───►      最终 8 层架构 + 发布验证
```

## 阅读顺序

1. 先读 [docs/architecture.md](../architecture.md) 了解最终架构与"phase → 合并位置"映射。
2. 按 Phase 1-10 顺序阅读本目录，理解每个技术壁垒的设计动机与演进。
3. Phase 11-15 按顺序阅读，对应 `backend/` 的实现框架（骨架 → Adapter → AssetStruct → DNA → MotionAlign/GImport）。
4. Phase 16-19 对应 `backend/app/runtime/` 的编排升级（编排 → Runtime → 产品 API → Foundation 模型层）。
5. Phase 20 对应 `backend/app/engines/foundation/training/` 的训练闭环（数据集 → 对比训练 → 注册表 → 模型服务 → GPU 分层）。
6. Phase 21 对应 `frontend/` 的三页产品（Creation Studio / Agent Timeline / Asset Viewer）+ 后端 zip 导出闭环。
7. Phase 22 对应 `backend/app/runtime/` 的平台升级（动态 Planner / 自评估 / MCP）+ `app/api/collab.py` 的协作层。
8. Phase 23 对应 `backend/app/engines/foundation/` 的创新层（knowledge / game_logic / simulation / benchmark）+ 两个新 Agent 与 API。
9. 配合 [README.md](../../README.md) Quick Start / Demo / Benchmark 验证最终落地；后端验证见 [backend/README.md](../../backend/README.md)。

## 完成情况

每个 Phase 文档均包含：目标 / 整体架构（ASCII 图）/ 模块设计 / JSON 示例 / API 接口 / 测试标准 / **合并位置映射表**（指向实际代码模块）。

- Phase 3 已去重（原文件内容重复两遍）。
- Phase 9 已补全缺失小节标题（"后续迭代增强"小节）。
