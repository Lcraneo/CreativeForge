# Phase 4 — Character DNA Engine

**Character Identity System：让一个 AI 生成角色成为可持续迭代、可动画化、可编辑的游戏角色资产。**

> AI 最大的问题不是生成不了图，而是无法稳定维护角色身份。第一次生成黑色短发 / 机械左眼 / 蓝色装甲 / 双刀，第二次让它攻击可能变成长发 / 红色装甲 / 单刀——名字还是同一个，视觉身份却变了。Character DNA Engine 解决这个问题。

## 1. 目标

建立 Character Identity System。

- 输入：角色资产
- 输出：Character DNA

以后所有操作（生成动作 / 修改装备 / 换姿态 / 换服装 / 表情变化）都必须经过 DNA 约束。

## 2. 整体架构

```text
              CreativeAsset v2
                     |
                     v
          +-------------------+
          | Character DNA     |
          | Engine            |
          +--------+----------+
                   |
     ------------------------------
     |              |             |
 Feature         Style        Structure
 Extraction      Embedding    Identity
     |              |             |
     ------------------------------
                   |
             Character DNA
                   |
        ----------------------
        |          |          |
    Generate    Edit       Animate
```

## 3. 在系统中的位置

```text
User Prompt -> Windup -> Raw Character -> AssetStruct
  -> Character DNA -> MotionAlign -> GameAssetCompiler -> GImport
```

DNA 必须在 AssetStruct 之后、MotionAlign 之前：AssetStruct 已知 Head / Body / Weapon / Layer，DNA 才能建立角色身份。

## 4. Character DNA 数据结构

新增 `character.schema.json`：

```json
{
  "character_id": "cat_warrior_001",
  "dna": {
    "visual_identity":    {},
    "style_identity":     {},
    "structural_identity": {},
    "semantic_identity":  {}
  }
}
```

### 4.1 Visual Identity

视觉身份。保存 Face Feature、Body Ratio、Color Signature。

```json
{ "face": { "eye_shape": "sharp", "hair": "short_black" } }
{ "body_ratio": { "head": 0.25, "body": 0.55, "leg": 0.20 } }
{ "color": ["#001122", "#0055FF", "#AAAAAA"] }
```

作用：防止第一次 Q 版比例、第二次真人比例；保持主色调。

### 4.2 Style Identity

解决"风格一致"——第一次日系二次元，第二次不能变成欧美写实。

```json
{ "style_embedding": { "anime": 0.95, "realistic": 0.12, "pixel": 0.05 } }
```

包含：绘画风格 / 光照风格 / 色彩风格 / 线条风格。

### 4.3 Structural Identity（游戏资产独有）

保存角色结构，支撑"换武器不是重新生成角色，而是 DNA + New Weapon → New Asset"。

```json
{ "structure": { "parts": ["head","body","weapon"], "equipment": ["sword","armor"] } }
```

### 4.4 Semantic Identity

保存角色语义，供 Agent 理解角色（如设计技能时读取 cat / warrior / damage / dual sword → 生成快速斩击技能）。

```json
{ "class": "warrior", "race": "cat", "role": "damage" }
```

## 5. DNA 提取流程

输入 `character.png`：

1. **Vision Understanding** → `{species:"cat", class:"warrior"}`
2. **Feature Extraction** → Face / Hair / Body / Color / Equipment
3. **Embedding Generation** → `character_vector`（如 `[0.231, 0.552, 0.821...]`）
4. **DNA Storage** → Character DNA

## 6. 角色生成约束流程

用户"给猫战士生成攻击动画"：

```text
Attack Request -> Character DNA -> Motion Generation
-> DNA Constraint -> Animation
```

生成过程中检查：Face Similarity（是否同一张脸）/ Style Similarity（是否同一种画风）/ Equipment Similarity（是否同一把武器）。

## 7. 角色编辑能力（产品体验重点）

用户"把猫战士的剑换成火焰刀"：

```text
传统 AI: 重新生成
我们:    DNA -> Lock(Face / Body / Style) -> Modify(Weapon) -> Generate New Asset
结果:    同一个角色 + 新武器
```

## 8. Character DNA API

```go
type CharacterDNAEngine interface {
    Extract(asset *CreativeAsset) (*CharacterDNA, error)
    Compare(dna1, dna2 *CharacterDNA) (float64, error)
    Constrain(generationRequest, dna) GenerationRequest
    Update(dna, change)
}
```

## 9. 工程目录

```text
character_dna/
├── extractor/   face.go  style.go  structure.go
├── embedding/   encoder.go
├── constraint/  dna_validator.go
├── storage/     dna_repository.go
├── models/      character_dna.go
└── tests/       similarity_test.go  consistency_test.go
```

## 10. 测试标准

| 测试 | 输入 | 检查 / 要求 |
| ---- | ---- | ---------- |
| 跨动作一致性 | Idle 角色 + Attack 角色 | DNA Similarity > 0.9 |
| 修改装备 | 原角色 + 新武器 | 保留 Face / Body / Style，变化 Weapon |
| 风格保持 | anime character | 输出 anime animation，不能 realistic |

## 11. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| 风格 / 颜色 / 结构身份 | `character_dna/` | 风格一致性并入 `precon/style/`；角色身份 / 版本记忆并入 `agent/memory/task_memory.py`（CreativeAsset 作为 evolving state，保存 asset versions / 检查点） |
| Embedding / 相似度 | `character_dna/embedding`、`storage` | 沿用 CreativeAsset `quality` + `provenance` 字段；长期记忆由 `agents/memory_agent/` 维护（跨任务风格一致） |
| 约束 / 校验 | `character_dna/constraint` | `agent/monitor/quality_gate.py`（统一质量阈值，触发 retry） |

见 [docs/architecture.md](../architecture.md) Layer 3（PReCon style 一致性）与 Layer 6/7（Memory）。
