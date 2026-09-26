# Phase 10 — 真实工程技术选型 + 项目仓库结构

**最终技术路线与项目仓库结构设计：Python 负责 AI Pipeline，Go 负责 Asset Runtime / 任务调度 / 高并发服务。**

> 虽 Holonic 使用 Go（高性能 / 服务稳定），但 CreativeForge 核心（Vision / AI Agent / CV / Diffusion / Embedding）生态全部集中 Python。第一版 Python 负责 AI Pipeline，Go 负责 Asset Runtime / 任务调度 / 高并发服务。

## 1. 最终技术路线确定

```text
Frontend  React + TypeScript
   |  WebSocket / REST
   v
Backend Gateway  FastAPI
   |
------------------------------------------------
Agent Layer        LangGraph Planner / Tool Router / Memory
------------------------------------------------
Asset Pipeline     Windup Adapter | AssetStruct Engine | Character DNA
                   | MotionAlign | GameAsset Compiler | GImport
------------------------------------------------
Storage            PostgreSQL | MinIO | Vector DB
```

## 2. 为什么选择 Python 后端

| 维度 | Go | Python |
| ---- | -- | ------ |
| 高性能 / 服务稳定 | ✔（Holonic） | |
| Vision / AI Agent / CV / Diffusion / Embedding 生态 | | ✔（CreativeForge 核心） |

第一版：Python 负责 AI Pipeline；Go 负责 Asset Runtime / 任务调度 / 高并发服务。

## 3. 项目仓库结构

```text
CreativeForge/
├── apps/
│   ├── backend/      main.py  api/  websocket/  config/
│   └── frontend/     src/  components/  pages/  stores/
├── core/
│   └── creative_asset/   models/  schema/  validator/  version/
├── pipeline/         processor.py  registry.py  executor.py
├── agents/
│   ├── planner/      planner.py
│   ├── router/       tool_router.py
│   └── memory/       asset_memory.py
├── engines/
│   ├── asset_struct/   segmentation.py  analyzer.py  extractor.py
│   ├── character_dna/  extractor.py  embedding.py  validator.py
│   ├── motion_align/   frame.py  align.py  event.py
│   ├── compiler/       compiler.py
│   └── gimport/        cocos.py  unity.py
├── adapters/
│   ├── windup/
│   ├── holonic/
│   └── external/
├── storage/
│   ├── database/
│   ├── object_storage/
│   └── vector/
├── tests/
└── docker/
```

## 4. 核心模块开发顺序

### 4.1 Sprint 0：基础设施

项目能运行。Backend FastAPI：`GET /health`、`POST /asset/create`、`GET /asset/{id}`。数据库 PostgreSQL：

```text
asset           id / project_id / name / type / version / status / created_at
asset_version   id / asset_id / version / processor / metadata / created_at
task            id / goal / status / plan / result        # Agent 使用
```

### 4.2 Sprint 1：CreativeAsset Core（第一优先级，对应 Phase 1）

```python
class CreativeAsset:
    identity; source; content; animation; engine; quality; provenance
```

实现 Validator（输入 `{"identity":{}}` 检查 Schema）。目录 `core/creative_asset/{models.py, validator.py, version.py}`。

### 4.3 Sprint 2：Agent Layer

实现真正 Agent。Planner 输入"生成一个火焰法师" → `{tasks:["generate","structure","dna","export"]}`。Tool Registry：

```python
TOOLS = {
  "generate":     GenerateTool(),
  "asset_struct": AssetStructTool(),
  "dna":          DNATool(),
  "export":       ExportTool(),
}
```

Agent 不写死流程：Task → Tool Selection → Execution。

### 4.4 Sprint 3：AssetStruct Engine（核心创新第一个）

```text
Image -> Vision Label -> SAM2 -> Layer
```

输入图片 → `asset/{body.png, weapon.png, effect.png, metadata.json}`。

### 4.5 Sprint 4：Character DNA（核心创新第二个）

第一版不做复杂模型，先 `{face, color, style, equipment}`；然后加入 Embedding。数据库新增 `character_memory`（id / asset_id / embedding / metadata）。

### 4.6 Sprint 5：MotionAlign（核心创新第三个）

MVP：Frame 读取 / Root 检测 / 基准点修正。输出 `{frames:10, anchor:{root:[100,200]}}`。

### 4.7 Sprint 6：GameAsset Compiler

生成 Cocos 资源：`export/{prefab, animation, atlas, metadata}`。

### 4.8 Sprint 7：GImport

实现 Cocos Adapter，自动生成 Cocos Project：`assets/{textures, animations, prefabs}`。

## 5. API 设计

创建资产：

```
POST /api/v1/assets/create
请求: { prompt:"机械猫战士", engine:"cocos" }
响应: { task_id:"xxx" }
```

## 6. Agent 执行流程

```text
Task Created -> Planner -> Generate Tool -> AssetStruct Tool
-> DNA Tool -> Compiler Tool -> GImport Tool
-> Validation -> Completed
```

## 7. 前端页面设计

MVP 只做三个页面：

1. **Workspace**——类似 AI IDE：项目（Cyber RPG）/ Characters（Cat Warrior / Mage / Monster）。
2. **Creation**——输入框"描述你的角色" + Generate；实时显示 Agent Planning / Generating / Structuring / Exporting。
3. **Asset Detail**——原图 / Layer / DNA / Animation / Export。

## 8. 第一版本必须完成的 Demo

用户"生成一个赛博朋克猫战士，横版动作游戏使用，需要 Cocos 导出" → 系统显示：

```text
Planner:    创建角色
  -> Windup:       生成图片
  -> AssetStruct:  拆分身体/武器
  -> DNA:          建立角色身份
  -> Compiler:     生成 Cocos 资源
  -> Export 完成
```

点击下载项目 → 打开 Cocos → 角色存在。

## 9. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| 最终仓库结构 | phase10 仓库结构 | 重构为最终 8 层（见 [README.md](../../README.md) 项目结构与 [docs/architecture.md](../architecture.md) Layer 1-10） |
| Backend / Frontend apps | `apps/backend`、`apps/frontend` | `studio/backend/`、`studio/frontend/`（FastAPI + React 18 + TS + Vite） |
| Agent Layer（planner/router/memory） | `agents/` | `agent/`（单 Agent）+ `agents/`（多 Agent）+ `protocol/` |
| Asset Pipeline engines | `engines/{asset_struct, character_dna, motion_align, compiler, gimport}` | `precon/`、`falign/`、`gimport/`（自研引擎层） |
| Storage | `storage/{database, object_storage, vector}` | MVP SQLite；`docker-compose.yml` + `docker/Dockerfile` 一键部署 |
| Demo / 发布验证 | phase10 demo | `examples/competition_demo/run_demo.py` + `tests/release/run_release_tests.py`（四层 L1-L4） |
| API 设计 | `POST /api/v1/assets/create` | `studio/backend`：`POST /api/tasks`、`GET /api/tasks/{id}`、`WS /ws/tasks/{id}/stream`、`GET /api/assets/{id}`、`POST /api/export`、`GET /api/benchmark` |

见 [docs/architecture.md](../architecture.md) Layer 8（Studio）与 Layer 10（Release & Demo）。
