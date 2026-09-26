# Phase 8 — CreativeForge Agent + Workspace + Benchmark

**Game Asset Production Agent：一句自然语言，Agent 自主拆解为任务图并调度自研技术链。**

> Phase 1 已建立 CreativeAsset 统一资产协议与 AssetProcessor / AssetAdapter 接口；Phase 8 在其上增加 CreativeForge Agent Layer——不是聊天机器人，而是 Game Asset Production Agent。

## 1. 最终系统架构

```text
                         User
                          |
                          v
                CreativeForge Agent
                          |
        ---------------------------------
        |               |               |
     Planner         Memory          Tool Router
        |               |               |
        ---------------------------------
                          |
                  Creative Workflow
---------------------------------------------------
Windup Adapter | AssetStruct Engine | Character DNA
| MotionAlign  | GameAsset Compiler | GImport Engine
---------------------------------------------------
                          |
                  Game Engine Project
```

## 2. CreativeForge Agent 的定位

不是聊天机器人，而是 Game Asset Production Agent。输入一句自然语言，例如"创建一个二次元机械猫战士，用于横版动作游戏，需要待机、攻击动画，并导入 Cocos"，Agent 自动拆解。

## 3. Planner Agent（核心）

负责目标 → 任务图。输入 `Create cyber cat warrior`，生成：

```json
{
  "goal": "Create playable 2D character",
  "tasks": ["generate_character","struct_asset","extract_dna","create_animation","compile_package","import_engine"]
}
```

## 4. Task Graph（动态任务图）

不使用固定流水线，升级为动态任务图：

| 用户意图 | Agent 路径 |
| -------- | ---------- |
| 给已有角色换武器 | Character DNA → Equipment Modify → Compiler（不重新生成） |
| 创建全新角色 | Windup → AssetStruct → DNA → Motion → Compiler |

Agent 根据目标选择路径。

## 5. Tool Router

负责选择工具。工具注册：

```json
{ "tools": [
  { "name": "windup_generate", "capability": "character_creation" },
  { "name": "asset_struct",    "capability": "layer_extract" },
  { "name": "dna_engine",     "capability": "identity" }
] }
```

Planner 查询"我要创建角色" → 匹配 windup_generate / asset_struct / dna_engine。

## 6. Memory System

解决长期项目。第一次创建 Cat Warrior（保存 `Character DNA: cat_warrior_001`），第二次"给它增加火焰技能" → Agent 读取 `cat_warrior_001` 而非重新生成。

分三层：

1. **Asset Memory**——角色 / 动画 / 版本 / 依赖。
2. **Project Memory**——游戏类型 / 引擎 / 风格 / 规范：`{engine:"cocos", style:"anime", camera:"side-scroller"}`。
3. **User Preference Memory**——用户偏好（日系风格 / 512 尺寸 / 横版角色）。

## 7. Workspace 设计

类似 AI 游戏开发工作台：

```text
CreativeWorkspace/
├── projects/
│   └── cyber_cat/
├── assets/         characters/  animations/  versions/  exports/
└── logs/
```

## 8. Asset Version System

AI 资产会不断修改：Cat Warrior v1 → v2 换装备 → v3 改颜色 → v4 动画优化。保存：

```json
{ "asset": "cat_warrior", "version": 4, "changes": ["weapon_replace","color_update"] }
```

## 9. Agent 执行日志

每次生成记录 `{task, tools[], result}`，用于调试 / 回滚 / 比赛展示。

## 10. Benchmark 设计

不能只展示"可以生成"，需要证明技术优势。

| Benchmark | 测试 | 指标 | Baseline | CreativeForge |
| --------- | ---- | ---- | -------- | ------------- |
| 角色一致性 | 同角色 Idle/Attack/Run 的 DNA Similarity | Character Consistency Score | 0.65 | 0.9+ |
| 资产生产效率 | 设计+切图+动画+导入耗时 | Asset Production Time | 小时级 | 分钟级 |
| 工程完整度 | Sprite/Layer/Animation/Collision/Prefab/Engine Import 是否支持 | — | — | 全部 ✓ |
| 修改成本 | 换武器 | Modification Cost | 重新制作 | DNA → Weapon Replace → Compile |

## 11. 最终 Demo 设计

比赛 / 产品展示时不展示"输入一句话生成图片"（竞争力弱），而是：

- **Demo 1 Create**：创建机械猫战士 → 展示 Planning → Generation → Struct → DNA → Animation → Import。
- **Demo 2 Modify**：换成火焰剑 → 读取 DNA → 锁定角色 → 修改装备 → 重新导入。
- **Demo 3 Engine**：Export Cocos → 打开 Cocos Creator → 角色已有动画 / 碰撞 / 可运行。

## 12. 最终项目架构

```text
CreativeForge AI
  Agent Layer
    |（CreativeAsset Contract）
  Generation Layer   Windup Adapter
    |
  Understanding Layer  AssetStruct Engine
    |
  Identity Layer       Character DNA
    |
  Animation Layer      MotionAlign
    |
  Compilation Layer   GameAsset Compiler
    |
  Deployment Layer     GImport Engine
    |
  Cocos / Unity
```

## 13. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| Planner / Tool Router / Memory / Workflow / Capability | `agent/` 各模块 | `agent/planner/`、`agent/executor/`、`agent/memory/`、`agent/capability/`、`agent/workflow/`、`agent/monitor/`、`agent/recovery/` + `agent/creative_agent.py` |
| Multi-Agent + 协议 | `agents/` + `protocol/` | `agents/`（supervisor / art / animation / engine / qa / memory）+ `protocol/`（message / state） |
| Workspace / 资产版本 / 执行日志 | `workspace/` | `studio/`（frontend + backend，7 页面 + REST + WS 事件流 + 真实 zip 导出）；资产版本由 `agent/memory/task_memory.py` 维护 |
| Benchmark | phase8 benchmark 草案 | 独立为 Phase 9 → `benchmark/` |

见 [docs/architecture.md](../architecture.md) Layer 6/7（Agent / Multi-Agent）与 Layer 8（Studio）。
