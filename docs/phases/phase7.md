# Phase 7 — GImport Engine

**CreativeForge 的最后一公里：将 AI 生成的 GameAsset Package 自动部署到游戏引擎工程。**

> 前面 Phase 2-6 已完成"AI 内容 → 标准化资产 → 游戏资源包"，但开发者仍需复制文件、创建 Prefab、绑定动画、配置组件、检查错误。Phase 7 的 GImport Engine 把 GameAsset Package 自动部署到游戏引擎工程，从 AI Content Generation 进入 AI Game Development Pipeline。

## 1. 定位

```text
传统流程: AI 生成角色 -> 导出图片 -> 美术处理 -> 程序导入
         -> 创建 Prefab -> 配置动画 -> 运行测试   (耗时小时甚至天)
CreativeForge: GameAsset Package -> GImport -> Playable Character
```

## 2. 整体架构

```text
              GameAsset Package
                     |
                     v
          +------------------+
          | GImport Engine    |
          +--------+---------+
     --------------------------
     v            v           v
 File Import   Scene Builder  Runtime Check
     v            v           v
 Texture       Prefab         Validation
     --------------------------
                     |
                     v
            Game Engine Project
        +---------+----------+
        v         v          v
      Cocos    Unity      Godot
```

## 3. 核心能力（四层）

```text
GImport Engine
├── Asset Import Layer
├── Engine Adapter Layer
├── Project Builder Layer
└── Runtime Validation Layer
```

## 4. 目录设计

```text
gimport/
├── core/        importer.go
├── adapter/
│   ├── cocos/   cocos_importer.go  prefab_builder.go
│   ├── unity/   unity_importer.go
│   └── godot/
├── builder/     project_builder.go  scene_builder.go
├── validator/   runtime_validator.go
└── manifest/    package_reader.go
```

## 5. 核心输入：GameAsset Manifest

Phase 6 输出，GImport 首先读取 `manifest.json`：

```json
{
  "name": "cat_warrior",
  "engine": "cocos",
  "resources": {
    "atlas": "cat.atlas",
    "animations": ["idle","attack"],
    "prefab": "cat.prefab"
  }
}
```

## 6. Import Pipeline

```text
GameAsset Package
  -> Manifest Parser
  -> Asset Dependency Resolver
  -> Engine Adapter
  -> Project Generator
  -> Runtime Validator
```

### 6.1 模块1：Manifest Parser

解析资产依赖：CatWarrior.prefab → Texture → Atlas → Animation → Collision，生成 `{dependencies:["texture","atlas","animation"]}`。

### 6.2 模块2：Dependency Resolver

解决资产关系：attack.anim → attack_frames → weapon_layer。自动检查是否完整，缺资源返回：

```json
{ "error": "MISSING_RESOURCE", "resource": "weapon_layer" }
```

### 6.3 模块3：Cocos Adapter（第一目标）

原因：项目方向是 2D 游戏资产，Cocos 对 Sprite / Animation / Prefab 支持成熟。

```text
GameAsset Package -> assets/ (textures spriteframes animations prefabs scripts)
```

自动创建 Prefab：

```text
CatWarrior Node
├── Sprite
├── Animator
├── Collider
└── EventSystem
```

### 6.4 模块4：Prefab 自动生成

输入 `{character:"cat_warrior", animation:["idle","attack"]}` → `CatWarrior.prefab`：

```text
CatWarrior
  ├── SpriteRenderer
  ├── AnimationController
  ├── Collider2D
  └── EventListener
```

### 6.5 Animation Binding

自动绑定：attack.anim → Animator → Attack State，生成 Animator Controller（Idle → Attack → Skill）。

### 6.6 Collision Binding

Phase 5 已生成 `{hitbox:{frame:5}}`；导入时自动生成 BoxCollider2D / PolygonCollider2D 并绑定 Animation Event → Enable Hitbox。

### 6.7 Unity Adapter（第二阶段）

```text
GameAsset -> Unity Adapter -> Assets/ (Prefab AnimatorController Texture ScriptableObject)
```

## 7. 统一 Engine Adapter 接口

```go
type EngineAdapter interface {
    Import(package GameAssetPackage) error
    CreatePrefab(asset CreativeAsset) error
    BindAnimation(animation Animation) error
    Validate() error
}
```

## 8. Runtime Validator

很多 AI 游戏生成项目缺失的能力。生成完成后自动测试：

1. **Asset Check**——Texture / Animation / Prefab 是否存在。
2. **Reference Check**——Prefab → Animation → Sprite 引用是否正确。
3. **Runtime Check**——启动 Demo Scene，检测角色是否显示 / 动画是否播放 / 碰撞是否正常。

```json
{ "status": "success", "runtime": true, "warnings": [] }
```

## 9. GImport API

```go
type GImportEngine interface {
    Import(pkg GameAssetPackage, engine string) error
    BuildPrefab(asset CreativeAsset) Prefab
    ValidateRuntime(project Project) ValidationResult
}
```

## 10. 完整 Demo 流程

用户"创建一个火焰法师，用于 Cocos 横版 RPG"：

| Phase | 产出 |
| ----- | ---- |
| Phase 2 | Windup 生成 `fire_mage.png` |
| Phase 3 | AssetStruct 拆 body / staff / fire_effect |
| Phase 4 | DNA 保存 FireMage Identity |
| Phase 5 | MotionAlign 生成 idle / attack / skill |
| Phase 6 | Compiler 输出 FireMagePackage |
| Phase 7 | GImport 自动：复制资源 → 创建 Prefab → 绑定动画 → 配置 Collider → 运行测试 |

最终 Cocos 中出现 `FireMage Character`，直接运行。

## 11. 技术壁垒

```text
普通 AI 游戏工具: Prompt -> 图片
CreativeForge:    Prompt -> Character -> Animation -> Prefab -> Playable Object
```

核心：从 AI Content Generation 进入 AI Game Development Pipeline。

## 12. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| Manifest / Dependency / Sprite Atlas / Animation Clip / Prefab | `gimport/` 各模块 | `gimport/manifest/`、`gimport/atlas/`、`gimport/animation/`、`gimport/prefab/` |
| Engine Adapter（Cocos / Unity / Godot） | `gimport/adapter/` | `gimport/adapters/`（同资产多引擎） |
| Runtime Validator / 一键导出 | `gimport/validator`、`gimport/exporter` | `gimport/validation/runtime_validator.py`、`gimport/exporter/one_click_export.py` |
| 串联 | `gimport/core`、`pipeline` | `gimport/pipeline/` |
| 契约检查 | `tests/` | `tests/test_gimport.md` |

见 [docs/architecture.md](../architecture.md) Layer 5（GImport）。
