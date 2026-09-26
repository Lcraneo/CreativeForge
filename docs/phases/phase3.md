# Phase 3 — AssetStruct Engine

**AI 2D 游戏资产结构化引擎：把 AI 生成的角色变成真正可以用于游戏开发的 2D Game Asset。**

> 这是整个项目从 Windup 类生成工具拉开差异的核心阶段。Windup 解决"生成一个好看的 2D 角色"；CreativeForge 解决"把 AI 生成的角色变成真正可以用于游戏开发的 2D Game Asset"。Phase 3 是项目第一个核心技术壁垒。

## 1. 目标

建立 AssetStruct Engine（AI 2D 游戏资产结构化引擎）。

- 输入：AI 生成角色图片，例如 `cat_warrior.png`
- 输出：Game Ready Character Asset = 角色主体 + 部件 + 图层 + Mask + Anchor + Metadata

## 2. 整体流程

```text
Raw Image
              |
              v
        +-----------------+
        | AssetStruct     |
        | Engine          |
        +--------+--------+
                 |
    +--------------+--------------+
    v              v              v
 Semantic       Layer         Geometry
 Understanding  Extraction   Analysis
    |              |              |
    v              v              v
 Character      Parts         Anchor
                 |
                 v
          Asset Metadata
                 |
                 v
          CreativeAsset v2
```

## 3. 为什么需要 AssetStruct

普通 AI 图片 `character.png` 对游戏不可直接使用。游戏需要：

1. **独立部件**——换武器：原图"猫战士 + 剑" → 游戏需要"猫战士" + "剑"分离。
2. **动画控制**——攻击：手臂移动 / 武器旋转 / 身体摆动，需要 Arm Layer / Weapon Layer / Body Layer。
3. **碰撞**——攻击范围：Sword → HitBox；身体：Body → HurtBox。

AssetStruct 是 AI Image → Game Object 的转换层。

## 4. AssetStruct Engine 架构

```text
asset_struct/
├── analyzer/      semantic_analyzer.go
├── segmentation/  mask_generator.go
├── layer/         layer_extractor.go
├── anchor/        anchor_detector.go
├── metadata/      asset_metadata.go
└── validator/     asset_validator.go
```

### 4.1 模块1：Semantic Analyzer

理解角色结构。输入 image，输出：

```json
{ "type": "character", "class": "warrior", "parts": ["head", "body", "weapon"] }
```

技术方案：视觉大模型（GPT Vision / Claude Vision）负责语义理解 + SAM 负责像素级分割。

```text
Vision Model  负责理解（这是头 / 这是武器 / 这是衣服）
     +
SAM           负责切割
```

### 4.2 模块2：Mask Generator

生成每个部件 Mask。

- 输入：`cat_warrior.png`
- 输出：`mask/{head.png, body.png, weapon.png, effect.png}`

流程：Image → Semantic Labels → SAM Segmentation → Mask。例：模型判断 `{weapon:["x:120","y:80"]}` → SAM 生成 `weapon_mask.png`。

### 4.3 模块3：Layer Extraction

游戏资产化关键。生成 Character / Head / Hair / Body / Weapon / Effect。

原图猫战士拆为：`layer_001.png` 头、`layer_002.png` 身体、`layer_003.png` 武器、`layer_004.png` 特效。

```json
{ "layers": [
  { "name": "weapon", "path": "weapon.png" },
  { "name": "body",   "path": "body.png" }
] }
```

### 4.4 模块4：Anchor Detector

游戏动画需要角色基准点。

```text
head
  |
 body
  |
root
```

自动检测：

```json
{ "anchor": { "root": [256,490], "hand": [330,260], "weapon": [400,220] } }
```

用途：后续 MotionAlign 动画绑定、引擎导入。

### 4.5 模块5：Asset Metadata Generator

```json
{
  "id": "cat_warrior_001",
  "type": "character",
  "size": [512,512],
  "layers": 8,
  "anchor": { "root": [256,490] },
  "engine_ready": true
}
```

此 Metadata 进入 CreativeAsset v2。

## 5. 完整数据流示例

用户"生成一个赛博朋克猫战士" → Windup 生成 `cat.png` → 进入 AssetStruct：

1. Semantic：识别 Character / Head / Body / Weapon / Armor
2. Segmentation：生成 head_mask / body_mask / weapon_mask
3. Layer：输出 head.png / body.png / weapon.png
4. Anchor：输出 root / hand / weapon
5. Metadata：输出 `{character:{parts:[head,body,weapon]}}`

最终产出 CreativeAsset v2。

## 6. AssetStruct 与 Windup 的区别（答辩重点）

```text
Windup:        Prompt -> Image
CreativeForge: Prompt -> Image -> Understanding -> Structure
                    -> Layers -> Animation Ready -> Engine Ready
```

一句话：**Windup 生成内容，CreativeForge 工程化内容。**

## 7. 核心创新点

1. **AI 生成资产结构理解**：普通 Image → 我们 Image → Game Object Graph。
2. **语义驱动自动拆层**：不是人工 PS 切图，而是 AI 理解角色组成 → 自动 Layer 化。
3. **游戏级 Metadata 自动生成**：Anchor / Collision 基础 / Layer 关系 / Animation 准备信息，让资产直接进入下一阶段。

## 8. 输出接口

```go
type AssetStructProcessor interface {
    Analyze(asset CreativeAsset)
    Segment(image Image)
    ExtractLayers(mask Mask)
    GenerateMetadata(layers []Layer)
}
```

## 9. 完成后的效果

输入一个 AI 生成角色，输出：

```text
CreativeAsset
├── character.json
├── layers/        body.png  weapon.png  effect.png
├── anchors.json
└── metadata.json
```

## 10. 在整个项目中的位置

```text
User -> Creative Agent -> Windup -> Raw Character
  -> AssetStruct -> Character DNA -> MotionAlign
  -> GameAsset Compiler -> GImport -> Cocos
```

Phase 3 后项目核心壁垒已经形成：① AssetStruct Engine（AI 图片 → 游戏资产结构）② Character DNA（角色跨动作一致性）③ MotionAlign（动画工程化）；GImport 作为产品落地能力。

## 11. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| 语义理解 + 分割 + 图层 | `asset_struct/` | `precon/`（grid / palette / contour / style / pipeline / quality）——"AI 图片 → 游戏资产结构"演化为 PReCon 像素重建管线，图层/Anchor/Metadata 概念下沉到 `gimport/manifest` 与 `gimport/prefab` |
| AssetStruct 处理接口 | `asset_struct/validator` | `adapters/creative_asset_adapter.py`（在 CreativeAsset.animation.frames 上运行切帧对齐，回写结果） |
| 契约检查 | `tests/` | `tests/test_precon.md`、`tests/test_adapter_contract.md` |

见 [docs/architecture.md](../architecture.md) Layer 3（PReCon）与 Layer 5（GImport）。
