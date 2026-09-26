# Phase 9 — CreativeForge MVP 工程落地规划

**用最小实现验证 CreativeForge 的核心价值，而不是堆功能。**

> Phase 1-8 是完整产品架构设计，直接全部实现会导致范围失控。Phase 9 进入真正工程阶段：核心验证"一句自然语言需求 → AI 资产生产 Agent → 生成一个可进入 Cocos 的 2D 游戏角色"。

## 1. MVP 原则重新定义

CreativeForge MVP **不追求**：自研大模型 ❌ / 完整 Unity+Cocos 双支持 ❌ / 全自动 3D ❌ / 超复杂动画系统 ❌。

MVP 只证明三个核心壁垒：**AI 生成 + 角色结构化 + 游戏资产导出**。

## 2. MVP 最终 Demo 链路

```text
User Prompt（"生成一个火焰法师角色，用于横版RPG"）
  -> Creative Agent
  -> Windup / SDXL API
  -> AssetStruct
  -> Character DNA
  -> Animation 处理
  -> Cocos Export
  -> Playable Character
```

## 3. 功能优先级划分

### 3.1 P0（必须实现）

| 模块 | 实现要点 |
| ---- | -------- |
| **Creative Agent** | LLM Planner + Tool Calling（LangGraph / LangChain / OpenAI Function Calling / Claude Tool Use）；输入"创建一个机械猫战士" → 输出任务计划 `{tasks:["generate","structure","dna","export"]}` |
| **Windup Adapter** | 证明不是简单调用 API；Generator Adapter → CreativeAsset v2；第一版一个生成接口 `generate_character()` → `{image, style}` |
| **AssetStruct Engine（核心）** | 第一个技术壁垒；输入角色图片 → 输出 `character/{body.png, weapon.png, effect.png, metadata.json}`；技术：Vision（GPT-4o/Claude Vision 理解"这是武器/身体/头"）+ SAM2（像素级 Mask）|
| **Character DNA Lite** | 不一开始做复杂 Embedding；先保存 `{style, colors[], parts[]}`；生成第二次时检查风格/颜色/部件 |
| **Cocos Export** | 区别"图片生成工具 vs 游戏资产工具"；输出 `CocosProject/{sprites, animations, prefab, metadata}` |

AssetStruct 技术流程：

```text
Image -> Vision Analysis -> SAM2 -> Layer Extraction
```

### 3.2 暂时模拟的模块（第一版不做）

| 模块 | 暂缓原因 | MVP 替代 |
| ---- | -------- | -------- |
| MotionAlign 完整版 | 动画 AI 本身复杂 | 预制动画 / AI 生成 sprite sequence / 简单帧处理；展示"角色生成 → 动画绑定 → 游戏运行"即可 |
| GameAsset Compiler | 简化 | JSON → Cocos 资源，不用真正 Compiler |
| GImport | 简化 | 提供 Export ZIP，而非自动打开编辑器 |

## 4. 48 小时版本（比赛 Demo）

| 阶段 | 完成内容 |
| ---- | -------- |
| Day 1 上午 | 项目骨架：`creativeforge/{agent, adapters, asset_struct, dna, exporter, frontend}` |
| Day 1 下午 | 实现 Agent：Prompt → Task Plan |
| Day 1 晚 | 接入图片生成 API：Prompt → Image |
| Day 2 上午 | 实现 AssetStruct：图片 → Layer |
| Day 2 下午 | 实现 DNA：保存 `character.json` |
| Day 2 晚 | Cocos Demo：Generate Character → Export → Run Game |

骨架目录：

```text
creativeforge/
├── agent/
├── adapters/
├── asset_struct/
├── dna/
├── exporter/
└── frontend/
```

## 5. 后续迭代增强

> 原 MVP 之上逐级增强，最终走向产品化。

### 5.1 Agent 升级

从固定流程升级为动态规划：修改角色 → 自动读取 DNA → 修改部件 → 重新导出；进一步成为自主游戏资产生产 Agent（用户"做一个横版 RPG 角色包" → 自动角色设计 / 技能设计 / 动画设计 / 资源导出 / 测试）。

### 5.2 AssetStruct 2.0

增加自动骨骼点 / Anchor / Collision；进一步实现 Layer Graph / Semantic Object Graph / Editable Character。

### 5.3 Character DNA 2.0

加入 Embedding：Image Encoder → Character Vector → Similarity Search；实现角色长期记忆（十次修改后仍保持同一角色）。

### 5.4 MotionAlign Lite → 2.0

Lite：帧检测 / Root 修正 / 动作分类。2.0：自动关键帧 / Root Motion / Hit Event / Timeline。

### 5.5 Workspace

增加项目管理（Project → Characters / Versions / Exports）。

### 5.6 Engine 生态

第一 Cocos → 第二 Unity → 第三 Godot。

## 6. 技术栈规划

| 层 | 选型 |
| -- | ---- |
| Backend | Python（AI 生态）：FastAPI / LangGraph / Pydantic / PyTorch / OpenCV |
| AI 视觉 | GPT Vision / Claude Vision |
| AI 分割 | SAM2 |
| AI Embedding | CLIP |
| AI 生成 | Windup / Stable Diffusion / FLUX |
| Frontend | React + Three/Canvas Preview + WebSocket Streaming |
| Storage | MVP SQLite；后期 PostgreSQL；对象 MinIO；向量 Milvus |

## 7. 最终 MVP 架构

```text
          React Web
              |
        FastAPI Backend
              |
        Agent Planner
              |
        Tool Router
--------------------------------
Windup Adapter | AssetStruct Engine
Character DNA  | Cocos Exporter
--------------------------------
              |
        CreativeAsset v2
              |
        Game Package
```

## 8. 项目开发顺序（最终确定）

不按 Phase 顺序编码，实际开发：

| Sprint | 完成内容 | 闭环 |
| ------ | -------- | ---- |
| Sprint 1 | Agent + Generation + AssetStruct | 第一个闭环 |
| Sprint 2 | DNA + Cocos Export | 核心 Demo |
| Sprint 3 | MotionAlign + Workspace + Benchmark | 产品 |

## 9. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| Benchmark 数据集 + 指标 + CF Score + 报告 CLI | phase9 benchmark | `benchmark/`：`dataset/`、`evaluation.py`、`metrics/`、`score.py`、`run_benchmark.py`、`results/` |
| MVP 工程目录骨架 | `creativeforge/{agent,adapters,asset_struct,dna,exporter,frontend}` | 重构为最终 8 层：`core/ protocol/ schemas/ packages/` + `adapters/` + `precon/ falign/ gimport/` + `agent/ agents/` + `studio/` + `benchmark/` |
| 开发顺序（Sprint 1-3） | phase9 开发顺序 | 对应 [docs/architecture.md](../architecture.md) Layer 1-10 与 Phase 6/7/8 验收 |

见 [docs/architecture.md](../architecture.md) Layer 9（Benchmark）。
