# Phase 2 — Windup Adapter v2

**外部生成能力接入层：让任何生成模型统一进入 CreativeAsset v2。**

> Windup 不再是产品主体，而是 2D 资产生成能力提供者。Phase 2 建立外部生成能力接入层，让 Windup / Stable Diffusion / FLUX / DALL·E / 用户上传都统一进入 CreativeAsset v2。

## 1. 目标

建立外部生成能力接入层：任何生成模型都可以统一进入 CreativeAsset v2。

## 2. 整体架构

```text
                  Creative Agent
                        |
                Asset Generation Task
                        |
        ---------------------------------
        |                               |
     Windup API                  Other Generator
        |                               |
        v                               v
  Windup Adapter               Generator Adapter
        |                               |
        ---------------------------------
                        |
                        v
                CreativeAsset v2
                        |
                        v
            AssetStruct / DNA / Motion
```

## 3. Windup Adapter v2 职责

不是简单调用 API，而是负责：

1. **请求转换**：CreativeForge 内部格式 → Windup 请求。
2. **结果解析**：Windup 返回 → CreativeAsset v2。
3. **元数据补充**：生成模型通常只给图片，Adapter 自动补 `source.provider` / `visual.style` 等。

```json
// CreativeForge 内部
{ "type": "character", "style": "anime", "action": ["idle", "attack"], "view": "side" }
// 转换为 Windup 请求
{ "prompt": "anime side view character", "animation": ["idle", "attack"] }
```

## 4. Adapter 接口设计

保持 Phase 1 的 AssetAdapter 思想（External Project → Adapter → CreativeAsset），Phase 2 扩展为生成能力接入：

```go
type AssetGeneratorAdapter interface {
    Generate(request GenerationRequest) (*CreativeAsset, error)
    Validate(asset CreativeAsset) error
    GetCapabilities()
}
```

### 4.1 GenerationRequest

Agent 不直接控制 Windup，中间增加 GenerationRequest 统一生成需求：

```go
type GenerationRequest struct {
    AssetType  string
    Style      string
    Character  *CharacterSpec
    Animation  []string
    Reference  []string
    Engine     string
}
```

例：用户"创建一个赛博朋克猫战士，横版动作游戏，需要攻击动画" → `{asset_type:"character", style:"cyberpunk", animation:["attack"], engine:"cocos"}`。

## 5. Windup Adapter 内部结构

```text
adapters/windup/
├── client/        windup_client.go
├── mapper/
│   ├── request_mapper.go      # CreativeForge -> Windup
│   └── response_mapper.go     # Windup -> CreativeAsset
├── models/         request.go  response.go
├── converter/      asset_converter.go
└── tests/          request_test.go  mapping_test.go
```

### 5.1 Request Mapper

CreativeForge → Windup：`{character:"fire mage", style:"pixel anime"}` → `{prompt:"fire mage character pixel anime", format:"sprite"}`。

### 5.2 Response Mapper

Windup `{image:"xxx.png"}` → CreativeAsset `{source:{type:"ai_generation", provider:"windup"}, visual:{style:"pixel anime"}}`。

## 6. 生成结果处理流程

```text
User Prompt -> Creative Agent -> GenerationRequest
-> Windup Adapter -> Windup -> Raw Image
-> Response Mapper -> CreativeAsset v2
-> AssetStruct (Layer Extraction) -> Character DNA -> MotionAlign
```

## 7. Asset Capability

Agent 未来需要自己选择工具，因此每个 provider 暴露能力清单：

```json
{
  "provider": "windup",
  "capabilities": ["character_generation", "sprite_generation", "animation_generation"]
}
```

Agent 规划示例：

```text
制作一个2D角色
Planner 查询能力：
  Windup: Character / Sprite / Animation
  SAM:     Segmentation
  OpenCV:  Frame Processing
然后规划：Windup -> AssetStruct -> MotionAlign
```

## 8. 完成后的能力

输入"创建一个 Q 版骑士角色，蓝色盔甲，需要 Idle 和 Attack 动画"：

```text
Prompt -> Creative Agent -> GenerationRequest -> Windup
-> Raw Asset -> Windup Adapter -> CreativeAsset v2
得到 { character:{dna:null, parts:null}, animation:["idle","attack"] }
```

然后交给 Phase 3 AssetStruct Engine 继续加工。

## 9. 与原 Phase 2 的区别

| 维度 | 原 Phase 2 | v2 |
| ---- | ---------- | -- |
| 定位 | Adapter = 数据搬运 | Adapter = 能力接入 + 数据标准化 + 能力描述 |
| 角色 | 传输层 | Agent 的工具层 |

## 10. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| 外部能力接入层 | `adapters/` | `adapters/windup/`、`adapters/holonic/`、`adapters/creative_asset_adapter.py`、`adapters/README.md` |
| Adapter 接口 / 注册表 | `contracts/` | `core/adapter.py`（`AssetAdapter` 接口）、`core/registry.py` |
| 能力映射 | `examples/windup_output.json` | `docs/mapping/windup_mapping.md`、`docs/mapping/holonic_mapping.md` |

见 [docs/architecture.md](../architecture.md) Layer 2。
