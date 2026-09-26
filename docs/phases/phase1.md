# Phase 1 — CreativeAsset v2 契约

**CreativeForge 统一资产协议：任何输入最终都转换为 CreativeAsset，后续所有模块只处理它。**

> Phase 1 建立 CreativeForge 的统一资产协议。一个 prompt、一张 AI 生成图、用户上传图、草稿、动画或参考角色，最终都归一为 CreativeAsset；Windup / AssetStruct / CharacterDNA / MotionAlign / GameAssetCompiler / GImport 全部只读写 CreativeAsset。

> 注：v1.0 已建立 AssetProcessor 统一处理接口、AssetAdapter 外部能力接入接口、Windup / Holonic / Cocos / Unity 接入思想；本阶段从 Pixel Asset Pipeline 升级为面向 AI 2D Game Asset Agent 的 CreativeAsset Contract v2.0。

## 1. 目标

建立整个 CreativeForge 的统一资产协议。

## 2. 整体数据流

```text
                 User
                  |
                  v
          Creative Agent
                  |
                  v
          Asset Requirement
                  |
                  v
          CreativeAsset v2
                  |
     -------------------------
     |              |          |
 AssetStruct   CharacterDNA   MotionAlign
     |              |          |
     -------------------------
                  |
          GameAssetCompiler
                  |
              GImport
                  |
            Cocos / Unity
```

## 3. CreativeAsset v2 总结构

```text
CreativeAsset
├── Identity       # 资产身份
├── Source         # 资产来源
├── Character      # 角色（核心新增）
├── Visual         # 视觉信息
├── Sprite         # 游戏实际使用资源
├── Layer          # 图层（核心新增）
├── Animation      # 动画（升级）
├── Collision      # 碰撞（新增）
├── Engine         # 目标引擎
├── Quality        # 质量评价
├── Provenance     # 来源追踪
└── Version        # 版本
```

### 3.1 Identity

资产身份信息，供所有模块唯一识别：

```json
{
  "asset_id": "character_cat_warrior_001",
  "type": "character",
  "category": "2d_game_asset"
}
```

### 3.2 Source

解决"这个资产从哪里来"。支持 AI 生成（`prompt`）、用户上传（`upload`）、二次修改（`variation`）：

```json
{
  "source_type": "prompt",
  "provider": "windup",
  "reference": []
}
```

### 3.3 Character（核心新增）

v1 仅有 Pixel + Animation；v2 把角色作为第一公民。

```text
Character
├── DNA          # Character Consistency Engine
├── Parts        # 角色组件（换武器 / 换服装 / 换发型）
├── Style
├── Appearance
└── Equipment
```

**Character DNA** 保存 `dna_id` / `face_embedding` / `style_embedding` / `body_ratio` / `color_signature`，保证 Idle / Attack / Run / Jump 都是同一个角色。

**Parts** 例如 `[{name:"head"}, {name:"weapon"}, {name:"armor"}]`，支撑后续换装。

### 3.4 Visual

```json
{
  "style": "anime",
  "color_palette": ["#FF0000"],
  "view": "side"
}
```

支持二次元 / 卡通 / 写实 / 像素。

### 3.5 Layer（核心新增）

对应 AssetStruct Engine：AI 图片自动拆分为 Character / Hair / Face / Body / Weapon / Effect 等图层。

```json
{ "layers": [ { "name": "hair", "mask": "hair.png" } ] }
```

### 3.6 Sprite

游戏实际使用资源：`sprite_sheet` + `frames`（x / y / w / h）。

### 3.7 Animation v2

```text
Animation
├── Action
├── Frames
├── Anchor
├── Motion
├── Events
└── Timeline
```

```json
{ "action": "attack", "events": [ { "frame": 5, "event": "hit" } ] }
```

### 3.8 Anchor

保存 `root` / `hand` / `weapon` 坐标，用于动画、碰撞、引擎导入。

### 3.9 Collision（新增）

```json
{ "collision": { "hitbox": [], "hurtbox": [] } }
```

攻击 → hitbox；身体 → hurtbox。

### 3.10 Engine

```json
{ "engine": { "target": "cocos", "format": "prefab" } }
```

第一阶段 Cocos，后续 Unity / Godot。

### 3.11 Quality / Provenance / Version

- Quality：`character_similarity` / `animation_score` / `engine_ready`
- Provenance：`history[]`（generate / split_layer …）用于版本管理
- Version：资产版本号

## 4. 完整 JSON 示例

```json
{
  "identity": { "id": "cat_warrior_001", "type": "character" },
  "source": { "provider": "windup", "prompt": "cyberpunk cat warrior" },
  "character": {
    "dna": { "dna_id": "dna_001" },
    "parts": ["head", "armor", "weapon"]
  },
  "layer": { "layers": ["body", "weapon", "effect"] },
  "animation": { "actions": ["idle", "attack"] },
  "engine": { "target": "cocos" }
}
```

## 5. 工程目录

```text
schemas/
  creative_asset.schema.json
  character.schema.json
  layer.schema.json
  sprite.schema.json
  animation.schema.json
  collision.schema.json
packages/creative-core/
  models/  interfaces/  validators/
examples/
  cat_warrior.json   mage.json
tests/
```

## 6. 完成标准

输入一个角色需求或一张 AI 生成图，转换为 CreativeAsset v2 JSON，并通过 Schema Validation。

## 7. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| CreativeAsset v2 契约 | `schemas/` | `schemas/creative_asset.schema.json`、`pixel.schema.json`、`animation.schema.json` |
| 核心接口 / 适配边界 | `packages/creative-core/` | `packages/creative-core/{interfaces,models}` + `core/adapter.py`、`core/registry.py` |
| 契约测试 | `tests/` | `tests/contract/`、`tests/test_adapter_contract.md` |

冻结契约见 [docs/architecture.md](../architecture.md) Layer 1。
