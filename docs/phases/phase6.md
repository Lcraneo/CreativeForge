# Phase 6 — GameAsset Compiler

**AI 游戏资产编译器：CreativeAsset v2 → GameAsset Package（开发者直接拖入游戏工程的完整资产）。**

> 目前资产状态（character.png / body.png / weapon.png / attack_frames/ / metadata.json）对游戏仍然是散乱文件；游戏需要 Character.prefab / .spriteatlas / .anim / Collision.json / Manifest.json。GameAsset Compiler 把 Raw Asset 编译为 Compiled Asset。

## 1. 定位

- 中文：AI 游戏资产编译器
- 输入：CreativeAsset v2
- 输出：GameAsset Package（开发者直接拖入游戏工程的完整资产）

## 2. 整体位置

```text
              CreativeAsset v2
                     |
                     v
          +--------------------+
          | GameAsset          |
          | Compiler           |
          +--------+-----------+
     --------------------------
     v            v            v
 Sprite        Animation     Engine
 Compiler      Compiler      Compiler
     v            v            v
 Atlas        Timeline       Prefab
     --------------------------
                     |
                     v
             GameAsset Package
                     |
                     v
             GImport Engine
```

## 3. GameAsset Package 设计

最终输出：

```text
CatWarrior/
├── assets/
│   ├── texture/    body.png  weapon.png
│   ├── atlas/      cat_warrior.spriteatlas
│   ├── animation/  idle.anim  attack.anim
│   ├── prefab/     cat_warrior.prefab
│   └── collision/  collision.json
├── metadata.json
└── manifest.json
```

## 4. Compiler 总架构

```text
game_asset_compiler/
├── sprite_compiler/      atlas_generator.go
├── animation_compiler/   animation_builder.go
├── prefab_compiler/      prefab_generator.go
├── collision_compiler/   collision_builder.go
├── manifest/             manifest_generator.go
└── validator/            package_validator.go
```

### 4.1 模块1：Sprite Compiler

把 Layer + Frame 转换为 Sprite Atlas：图片 → 裁剪 → 排列 → 压缩 → Atlas。输出 `cat_warrior.atlas`（20 张图 → 1 张 Sprite Sheet）。

```json
{ "atlas": { "width": 2048, "height": 2048, "sprites": [
  { "name": "attack_001", "x": 0, "y": 0 } ] } }
```

用途：减少 Draw Call 与加载次数。

### 4.2 模块2：Animation Compiler

对应 Phase 5。输入 MotionAlign 输出，生成游戏动画（Unity Animator Controller / Cocos AnimationClip）：

```json
{ "animation": "attack", "duration": 0.5, "timeline": [ { "frame": 5, "event": "hit" } ] }
```

### 4.3 模块3：Prefab Compiler

自动生成游戏对象。以前程序员手动"创建角色 → 挂 Sprite → 绑定动画 → 添加碰撞"；现在 Compiler 自动。输入 Character DNA + Layer + Animation + Collision → `CatWarrior.prefab`：

```text
CatWarrior
├── Root
│   ├── Body Sprite
│   ├── Weapon Sprite
│   ├── Animator
│   ├── Collider
│   └── Event Receiver
```

### 4.4 模块4：Collision Compiler

来自 AssetStruct + MotionAlign，生成游戏碰撞。角色：`{hurtbox:{type:"capsule"}}`；攻击：`{hitbox:{frame:5, shape:"polygon"}}`。最终 Attack Frame5 → Activate HitBox → Damage Event。

### 4.5 模块5：Manifest Generator

所有资产需要索引，用于版本管理 / 增量更新 / 云端同步：

```json
{ "name": "cat_warrior", "version": "1.0", "files": ["prefab","atlas","animation"] }
```

## 5. Engine Adapter 设计

Compiler 不直接绑定引擎，采用 Engine Adapter（Cocos / Unity）：

```go
type EngineAdapter interface {
    CompilePrefab(asset CreativeAsset) File
    CompileAnimation(animation Animation) File
    Validate(package GameAssetPackage) error
}
```

### 5.1 Cocos 输出（第一阶段）

原因：2D 优势明显、国内游戏生态、比 Unity 接入成本低。

```text
assets/
├── textures  spriteFrames  animations  prefabs  scripts
```

### 5.2 Unity 输出（第二阶段）

```text
Assets/
├── Texture  Animator  Prefab  Materials  Scripts
```

## 6. 工作流示例

用户"创建一个火焰法师，横版 RPG，Cocos 使用"：

前面 Windup 生成角色；AssetStruct 拆 body / staff / effect；Character DNA 保存 Fire Mage Identity；MotionAlign 生成 idle / attack / skill。进入 Compiler：

1. 生成 Atlas `mage_atlas.png`
2. 生成 Animation `idle.anim` / `attack.anim`
3. 生成 Prefab `FireMage.prefab`
4. 生成 Manifest `{asset:"fire_mage", engine:"cocos"}`

最终 `FireMage.zip` 直接导入。

## 7. Compiler API

```go
type GameAssetCompiler interface {
    Compile(asset *CreativeAsset) (*GameAssetPackage, error)
    GenerateAtlas(sprites []Sprite) Atlas
    GenerateAnimation(motion MotionData) Animation
    GeneratePrefab(asset CreativeAsset) Prefab
    ValidatePackage(pkg GameAssetPackage) bool
}
```

## 8. 核心创新

传统 AI 生成：图片 → 结束。CreativeForge：

```text
AI 生成: 图片 -> 结构 -> 角色 -> 动画 -> 碰撞 -> Prefab -> 游戏资产包
```

核心价值：**将生成式 AI 输出转换为符合游戏引擎规范的可执行资产。**

## 9. 完成后的项目能力

用户"创建一个二次元机械骑士，用于横版动作游戏，需要待机、攻击动画，导入 Cocos" → 系统自动 Windup → AssetStruct → CharacterDNA → MotionAlign → GameAsset Compiler → Cocos Package。最终得到：

```text
MechanicalKnight.zip
├── prefab  animations  atlas  collision  metadata
```

## 10. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| Atlas / Animation / Prefab / Manifest 编译 | `game_asset_compiler/` | `gimport/atlas/`、`gimport/animation/`、`gimport/prefab/`、`gimport/manifest/`（编译能力下沉进 GImport 一键导入管线） |
| Collision / Package 校验 | `game_asset_compiler/validator` | `gimport/validation/runtime_validator.py` |
| Engine Adapter | `game_asset_compiler/engine` | `gimport/adapters/`（Cocos / Unity / Godot） |
| 契约检查 | `tests/` | `tests/test_gimport.md` |

见 [docs/architecture.md](../architecture.md) Layer 5（GImport）。
