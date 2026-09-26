# CreativeForge Backend (Phase 11-23)

真实可扩展的服务端：**FastAPI → Agent Runtime（DAG 并行编排）→ 引擎链 → CreativeAsset → PostgreSQL**。
不是一次性 Demo —— 所有能力（生成 / 结构化 / DNA / 动画 / 战斗 / 引擎导入）都是注册式插件，按 Phase 11-19 的框架逐级升级；Phase 16 起由 Agent Runtime 自主调度。

## 快速开始

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env            # 默认 SQLite 即可跑通；PostgreSQL 见下
python -m uvicorn app.main:app --port 8765
# Swagger: http://127.0.0.1:8765/docs
```

PostgreSQL（推荐生产形态）：

```bash
docker compose up -d              # postgres + backend
```

## 端到端链路

```text
用户 Prompt
   ↓
FastAPI  POST /api/v1/assets/create
   ↓
Agent Planner        创建 / 修改意图 → 任务链 + 引擎目标
   ↓
Tool Router          generate_asset → structure_asset → create_dna
                     → motion_align → gimport（修改链路先 find_character）
   ↓                       ↓
Windup Adapter        AssetStruct / CharacterDNA / MotionAlign / GImport
（真实 API 或 mock）    Phase 13-15 引擎
   ↓
CreativeAsset v1（冻结契约）
   ↓
PostgreSQL           assets / asset_layers / asset_nodes / character_dnas
                     / character_embeddings / character_versions
                     / animation_clips / animation_events / tasks
```

## API

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| POST | `/api/v1/assets/create` | `{prompt, engine?}` → 任务计划 + 全链路结果 + asset_id |
| GET  | `/api/v1/assets` | 资产列表 |
| GET  | `/api/v1/assets/{id}` | 完整 CreativeAsset（metadata_json） |
| GET  | `/api/v1/tasks/{id}` | Agent 执行记录（plan / result） |
| POST | `/api/v1/dna/create` | `{asset_id}` → character_id（已有则复用） |
| GET  | `/api/v1/dna/{character_id}` | 身份 + 向量元信息 + 版本谱系 |
| POST | `/api/v1/dna/search` | `{image}` → 同角色判定（cosine > 阈值） |
| GET  | `/health` | 健康检查 |

示例（Phase 11 验收形态）：

```json
POST /api/v1/assets/create
{"prompt": "创建一个机械猫战士，带火焰剑攻击，导入cocos"}

→ {
  "task_id": "…",
  "plan":   {"mode": "create_character",
             "tasks": ["generate_asset","structure_asset","create_dna","motion_align","gimport"],
             "engine": "cocos"},
  "result": {"generate_asset": {"image": "…png", "style": "anime"}, …},
  "asset_id": "…"
}
```

修改同一角色（Phase 14 身份保持）：`给机械猫战士换一把火焰剑` → Planner 判定
`modify_existing_character`，先 `find_character` 命中 DNA，再生成 `…_v2.png`，
cosine 相似度 > 0.85 判定为同一角色，版本记入 `character_versions`。

## Agent Runtime（Phase 16-17）

`create` 端点已升级为 Agent Runtime：用户只描述目标，系统自主决定调用什么模块、按什么顺序、失败怎么办。

```text
用户目标
   → Intent Analyzer     runtime/intent.py      意图 / 引擎 / 风格 / 需求
   → Planner Runtime     runtime/planner.py     动态决策（记录 decisions）→ DAG 计划
   → Agent Executor      runtime/executor.py    驱动 DAG，逐步 checkpoint
        并行分支：AssetStructAgent → {DNAAgent ∥ MotionAgent} → CombatAgent
        尾链：     → ExportAgent → QualityAgent
   → Quality Gate        四面检查（结构 / DNA / 动画残差 / 引擎清单）
   → Self Healing        runtime/healing.py     一次修复轮，失败则明确上报
   → Human Review        runtime/review.py      WAITING_REVIEW → approve → 断点续跑
   → Memory              runtime/memory.py      用户偏好（DB 持久化）+ 过程记忆
```

- 七个领域 Agent 各管一项专业能力，包装 Phase 11-15 的工具（引擎仍是唯一事实源）
- MCP 风格工具 Schema（`runtime/registry.py`），Planner 按能力匹配选路
- 审核点：`POST /api/v1/tasks/{id}/approve` 从 checkpoint 恢复，已完成节点不重跑
- `GET /api/v1/tasks/{id}` 返回执行轨迹（每步 agent / 耗时 / 摘要），支撑前端 Agent 可视化
- `POST /api/v1/assets/export`（Phase 18.10）：已有资产一键切换引擎重新导出（cocos / unity / godot）

## 模型训练与部署（Phase 20）

资产库第一次成为训练数据源：从 DB 资产挖掘角色身份数据集，训练 DNA 投影头并注册部署，全程确定性可复现。

```text
POST /api/v1/models/train
   ↓
Dataset        dataset.py        同角色跨版本/视角 → 正样本对，跨角色 → 负样本对
   ↓                             （spec 三 目录结构：metadata/skeleton/animation/engine）
Preprocess     质量过滤            engine manifest 分数 < 1.0 的样本剔除
   ↓
Features       encoder.py        DINOv2+CLIP 双分支替身：32 身份维 + 32 噪声维
   ↓
Training       trainer.py        对比损失（margin）真实梯度下降，对角投影头，无 RNG
   ↓
Evaluation     evaluation.py     正/负对余弦、margin、检索命中率（训练前后对比）
   ↓
Registry       registry.py       注册 staged → promote production → 归档旧版本
   ↓
Serving        model_service.py  /models/dna/embed 经 GPU 队列用 production 权重推理
```

实测（两个角色 3 张图 × 3 视角）：正对余弦 0.684 → 0.978，margin 0.671 → 0.843，
loss 1.83 → 0.009，管线 <0.2s。真实 DINOv2/CLIP 主干替换时只换 `encoder.py` 的
特征提取，训练 / 注册 / 部署链路零改动。

API（`/api/v1/models`）：

| 方法 | 路径 | 说明 |
| ---- | ---- | ---- |
| POST | `/api/v1/models/train` | 资产库 → 训练管线 → 注册 + 生成环境（production） |
| GET  | `/api/v1/models/registry` | 模型产物清单（metrics / config / status） |
| GET  | `/api/v1/models/runs` | 训练运行记录 |
| POST | `/api/v1/models/dna/embed` | 图片 → DNA 向量（GPU 层，production 投影头） |
| POST | `/api/v1/models/quality/check` | 资产 → 一致性 / game-ready 检查 |
| POST | `/api/v1/models/motion/analyze` | 资产 → 逐剪辑动画语义（动画知识库） |
| GET  | `/api/v1/models/tiers` | GPU/CPU 任务分层映射 |

GPU/CPU 冷热分层（spec 十七）：执行轨迹每个步骤记录 `tier`；`GpuQueue`
单工作替身串行化重推理，后续替换为 Celery/Ray worker 池。

## 研究创新层（Phase 23）

从"AI 驱动的资产生产平台"升级为 Game Creation Intelligence System——AI 开始
理解资产关系、游戏规则与玩法需求：

- **Knowledge Graph + RAG（23.1-4）** — `foundation/knowledge.py` 从资产库
  挖掘图谱：`Character --HAS_WEAPON--> Weapon --TRIGGERS--> Skill
  --NEEDS--> Animation`、`HAS_SKILL`（逻辑蓝图）、`EXPORTED_TO`（引擎）；
  `KnowledgeRetriever` 把关系事实 + DNA 元数据打包成上下文注入执行环境
  （向量腿随真实文本编码器接入）。`GET /api/v1/knowledge/graph` 输出全图。
- **Game Logic Generation（23.5-7）** — `foundation/game_logic.py` 的
  CreativeSkill 蓝图协议：目标 → 技能类型/元素解析 → 数值生成（冲刺 =
  damage 20 / cooldown 3 / `dash_attack` / `blue_flash`，与规格示例完全
  一致）→ Cocos 动画事件绑定 + Unity C# 组件脚本。
  **GameLogicAgent**（`change=skill` 链路）挂载蓝图并同步战斗技能表。
- **Game Simulation（23.8-9）** — `foundation/simulation.py` 三平面检查：
  physics（冲刺距离）/ gameplay（伤害上下限、冷却覆盖动画时长）/
  performance（帧预算）；超纲数值自动修复并记录 before/after（火球
  87.5 → 80），修复同步回战斗技能表。**SimulationAgent** 出具报告。
- **Agent Evaluation + Benchmark（23.10/23.13）** — 每个任务附带
  `evaluation {identity, animation, engine}` 记录（反馈闭环数据点）；
  `POST /api/v1/benchmark/run` 计算 Asset / Game / Agent 三平面分数与
  CF Game Score（Asset .5 / Game .3 / Agent .2）。
- **build_dag 修复** — 无并行分支的短链路此前头尾断连（quality_check
  会提前空跑），现强制 `head[-1] -> tail[0]` 连接，style / skill 链路
  变为真正的线性 DAG。

## 高级 Agent 平台（Phase 22）

从"固定流程 Agent"升级为"自主决策型 Agent 平台"：

- **Dynamic Planner（22.1）** — Intent Analyzer 增加修改类型分类
  （`change: style / weapon / motion / full`）。风格修改走最小链路
  `find_character → modify_style → quality_check`（StyleAgent 只改调色板，
  动画 / 战斗 / 引擎载荷整体继承上一版），武器 / 动作修改仍走完整身份保持
  管线；规划决策记录跳过了哪些阶段。
- **Asset Context Retriever（22.1）** — `find_character` 命中时加载该角色
  最新完整资产到 `context["previous_asset"]`，短链路靠它携带历史。
- **Self Evaluation（22.4）** — 每个步骤摘要附加确定性 `confidence`
  （`runtime/evaluation.py` 从 segmentation / 残差 / manifest 分数提取）；
  低于 0.8 的节点触发一次自愈重跑（轨迹记录 `self_evaluation` 步骤），
  重跑仍低则如实上报。
- **MCP Tool Ecosystem（22.3）** — `GET /api/v1/mcp/tools` 输出机器可读
  清单（管线工具 invocable=false 供 Planner 能力匹配；独立工具
  `export_cocos/unity/godot`、`dna_embed`、`asset_quality`、
  `motion_analyze`、`train_dna_encoder` 可经 `POST /api/v1/mcp/invoke`
  直接调用）；新引擎 / 模型服务注册即自动进入清单。
- **Collaboration + Tenancy（22.6 / 22.8）** — `projects` +
  `project_members`（owner / reviewer / developer / designer）+
  资产生命周期状态机 `submit → in_review → approve → approved →
  promote → production`，每步按角色守卫（403 / 409）；项目带
  `tenant_id` 多租户隔离。

## 产品 MVP（Phase 21）

规格十四的三页前端落在 `frontend/`（React 18 + Vite + Tailwind 4，
`npm run dev` 走 5173 代理到本服务）：

| 页面 | 能力 |
| ---- | ---- |
| Creation Studio | Prompt + Engine/Style 参数 → `POST /create`，一键生成 |
| Agent Timeline | DAG 分层视图（✓/⟳/○ + GPU/CPU 徽章）+ 执行轨迹 + 规划决策 + 审核通过 |
| Asset Viewer | 六层 DNA / 图层 / 调色板 / 动画 clips / 战斗技能 / 引擎导出 + zip 下载 |

后端补全导出闭环：`GET /api/v1/assets/{id}/export.zip?engine=cocos` 把
引擎资源树打包为真实 zip（DNA.json / skill.json / collider.json /
textures / spriteframes / animations / prefab），纹理为占位 PNG，纯
stdlib 生成。

## 模块 → Phase 对照

| 模块 | Phase | 说明 |
| ---- | ----- | ---- |
| `app/core/` | 11.4-11.5 | 配置 + async SQLAlchemy 引擎 |
| `app/models/` | 11.6 / 13 / 14 / 15 | Asset、Task、图层/图、DNA、版本、动画剪辑/事件 |
| `app/agent/` | 11.7 | Planner（规则式，LLM 可替换）+ Tool Router |
| `app/tools/` | 11.8-11.9 | BaseTool 插件 + 注册表 + 6 个管线工具 |
| `app/adapters/` | 12 | AssetAdapter 接口、Windup client/mock/mapper、Holonic 桩 |
| `app/engines/asset_struct/` | 13 | Vision Analyzer → SAM2 → Layer → Asset Graph → 锚点/像素/质量 |
| `app/engines/character_dna/` | 14 | Encoder → Vector Store → 相似检索 → DNA 记忆 → 版本图 |
| `app/engines/motion_align/` | 15.1-15.3/15.5 | Pose → Anchor Solver → 切帧/裁剪/锚点填充 → 图集 → Timeline/事件/状态机 → Hitbox |
| `app/engines/gimport/` | 15.4 | EngineExporter 接口 + Cocos/Unity 导出器 + GImport Processor |
| `app/services/` | 11.10 | 编排 + 全部落库 |
| `app/api/` | 11.11 / 14.12 / 18 | assets / tasks / dna 路由 + approve / export |
| `app/runtime/` | 16-17 | Intent → Planner → DAG → 七领域 Agent → Quality → Healing → Review → Memory |
| `app/engines/foundation/` | 19 | 六层 DNA profile / 一致性评估模型 / 动画知识库 |
| `app/engines/foundation/training/` | 20 | 身份数据集挖掘 → 对比训练 → 评估 → 模型注册表 + 部署管线 |
| `app/models/training.py` | 20 | model_artifacts（staged→production→archived）/ training_runs |
| `app/api/models.py` + `app/services/model_service.py` | 20 | 模型服务：train / registry / runs / dna embed / quality check / motion analyze |
| `app/runtime/tiers.py` | 20 | GPU/CPU 任务分层（步骤记录 tier）+ GPU 队列 |
| `app/api/asset.py` + `app/services/export_service.py` | 21 | `GET /{id}/export.zip`：引擎资源树 + DNA/skill/collider → 真实 zip 下载 |
| `app/runtime/`（planner / intent / evaluation / style 链路）+ `app/runtime/agents/style.py` | 22 | 动态 Planner 短链路 + StyleAgent + 置信度自评估与自愈 |
| `app/api/mcp.py` | 22 | MCP 工具清单 + invoke（export_* / dna_embed / quality / motion / train） |
| `app/api/collab.py` + `app/models/collab.py` | 22 | 项目 / 成员角色 / 资产生命周期状态机 / 多租户 |
| `app/engines/foundation/{knowledge,game_logic,simulation,benchmark}.py` | 23 | 知识图谱 + 检索 / CreativeSkill 蓝图 + 引擎脚本 / 三平面模拟器 / 评分体系 |
| `app/runtime/agents/{logic,simulate}.py` + `app/tools/{logic,simulate}_tool.py` | 23 | GameLogicAgent / SimulationAgent（skill 修改链路） |
| `app/api/{knowledge,benchmark}.py` | 23 | 知识图谱查询 + Game Creation Benchmark |
| `app/models/runtime.py` | 17 | agent_tasks（状态机 + checkpoint）/ user_preferences |

## 模型替换点（MVP → 真实能力）

所有确定性实现都藏在被冻结的接口后面，替换时管线零改动：

- `adapters/windup/client.py` `WindupClient` — 配置 `WINDUP_BASE_URL` 即切换真实生成 API（当前为 MockWindupClient）
- `engines/asset_struct/analyzer/vision_analyzer.py` — 换 GPT-4.1 Vision / Claude Vision
- `engines/asset_struct/segmentation/sam_processor.py` — 换真实 SAM2
- `engines/character_dna/encoder/clip_encoder.py` — 换真实 CLIP；`vector/store.py` 换 Milvus/Chroma
- `engines/motion_align/detector/pose_detector.py` — 换 MediaPipe Pose
- `engines/motion_align/sprite/` + `layers/` — 接 Pillow 后做真实像素裁剪/Alpha 提取
- `engines/gimport/exporter/` — Cocos / Unity / Godot 导出器已就位，新引擎按同一 `EngineExporter` 接口注册

## 验证

```bash
python tests/run_backend_tests.py
# 40/40 checks passed —— Phase 11-15：创建链路、身份保持修改链路、
# Anchor 对齐残差、图集打包、事件绑定、DNA 谱系与相似检索、引擎资源树、状态机

python tests/run_runtime_tests.py
# 36/36 checks passed —— Phase 16-19：DAG 并行编排、执行轨迹、Combat skill、
# 质量门、六层 DNA profile、一致性评估、审核暂停 + 断点续跑、偏好记忆、
# 自愈重试、导出中心（unity/godot）、动画知识库

python tests/run_training_tests.py
# 30/30 checks passed —— Phase 20：数据集挖掘与质量过滤、对比训练收敛、
# 训练前后评估、注册表晋升与版本归档、模型服务（embed/quality/motion）、
# GPU 队列与任务分层、确定性复训

python tests/run_phase21_tests.py
# 19/19 checks passed —— Phase 21：export.zip（cocos/unity）完整性、
# PNG 占位图、DNA/skill/collider 载荷、POST /export 回归、CORS

python tests/run_phase22_tests.py
# 34/34 checks passed —— Phase 22：风格修改短链路（StyleAgent + 上一版
# 载荷继承 + 版本谱系）、置信度自评与低置信自愈、MCP 清单与 invoke、
# 项目协作角色守卫（403/409）、多租户过滤

python tests/run_phase23_tests.py
# 25/25 checks passed —— Phase 23：知识图谱挖掘与关系查询、冲刺技能
# 蓝图（规格数值逐一命中）、火球超纲伤害自动修复、引擎脚本生成、
# 任务级 evaluation、Game Creation Benchmark（Asset/Game/Agent/CF）
```
