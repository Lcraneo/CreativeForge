# Phase 5 — MotionAlign Engine

**AI 生成 2D 动画的时空理解与游戏化标准化引擎：AI Animation → Game Animation。**

> AI 可以生成动作，但结果通常帧间角色漂移、身体比例变化、动作节奏不稳定、无法直接作为游戏动画、缺少攻击判定与事件节点。MotionAlign 的目标是把 AI Animation 转换为 Game Animation。

## 1. 目标

建立 MotionAlign Engine（AI 生成 2D 动画的时空理解与游戏化标准化引擎）。

## 2. 在整体架构的位置

```text
User -> Creative Agent -> Windup Adapter -> Raw Asset -> AssetStruct
  -> Character DNA -> [MotionAlign]
  -> GameAsset Compiler -> GImport -> Cocos / Unity
```

## 3. 总体架构

```text
              Animation Input
                     |
                     v
          +-----------------+
          | MotionAlign     |
          | Engine          |
          +-------+---------+
     --------------------------
     v            v           v
 Frame Analysis  Motion     Animation
                 Alignment  Understanding
     v            v           v
 Frame          Root        Event
 Structure      Sync        Generation
     --------------------------
                     |
                     v
            Game Ready Animation
```

## 4. 核心模块

```text
motion_align/
├── frame/        frame_analyzer.go
├── alignment/    root_alignment.go  scale_alignment.go
├── motion/       motion_analyzer.go
├── action/       action_segmenter.go
├── event/        event_generator.go
└── quality/      animation_validator.go
```

### 4.1 模块1：Frame Analyzer

理解每一帧。输入 `attack.gif` 或 `frame_001.png ... frame_NNN.png`，输出：

```json
{ "frames": 10, "character": "cat_warrior", "key_points": ["head","hand","foot"] }
```

关键点检测依赖 Phase 3 已生成的 Character Anchor（`root` / `hand` / `weapon`）。MotionAlign 每帧重新检测，发现漂移：Frame1 root(256,490) → Frame2(262,510) → Frame3(270,530) → 角色向下漂移。

### 4.2 模块2：Root Alignment（核心）

问题：AI 动画每帧角色基准点偏移，导致游戏中角色抖动。

| | Frame1 | Frame2 | Frame3 |
| -- | -- | -- | -- |
| 原 root | (100,300) | (110,320) | (90,290) |
| 修正 root | (100,300) | (100,300) | (100,300) |

统一角色基准点。

### 4.3 模块3：Scale Alignment

解决角色大小变化：Frame1 100px / Frame2 120px / Frame3 90px → 统一比例。输出 `{scale: 1.0}`。

### 4.4 模块4：Motion Analysis

不仅知道第几帧，还知道角色做什么。攻击动作分段：Frame1 准备 / Frame2 蓄力 / Frame3 挥刀 / Frame4 命中 / Frame5 恢复。

```json
{ "motion": "attack", "phases": ["prepare","strike","recover"] }
```

### 4.5 模块5：Action Segmentation

动作分段。第一阶段支持 Idle / Run / Attack / Jump / Hit / Death。输入 10 帧动画：

```json
{ "action": "attack", "segments": [
  { "start": 0, "end": 2, "phase": "prepare" },
  { "start": 3, "end": 5, "phase": "strike" }
] }
```

### 4.6 模块6：Animation Event Generator

游戏开发最需要的能力。传统需要程序员手动设置"第5帧攻击生效"，MotionAlign 自动生成：检测武器轨迹，发现 Frame4-5 Sword reaches enemy → 生成事件。

```json
{ "events": [ { "frame": 5, "event": "attack_hit" } ] }
```

支持 `attack_start` / `attack_hit` / `foot_step` / `skill_effect` / `sound_trigger` / `animation_end`。

### 4.7 模块7：Animation Quality Validator

生成评分，低于阈值重新优化：

```json
{ "quality": { "root_stability": 0.94, "motion_smooth": 0.91, "character_similarity": 0.96 } }
```

## 5. 完整流程示例

用户"给猫战士生成攻击动作"：

1. Windup 生成 attack_frames
2. MotionAlign 输入 frame1..frame8
3. Frame Analysis 识别 head / body / weapon / root
4. Root Alignment 修正漂移
5. Action Understanding 识别 prepare / strike / recover
6. Event Generation 生成 `{hit_frame:5}`
7. Attack Animation → Game Ready

## 6. MotionAlign API

```go
type MotionAlignEngine interface {
    AnalyzeFrames(frames []Frame) (*MotionData, error)
    AlignRoot(motion MotionData) MotionData
    SegmentAction(motion MotionData) []ActionPhase
    GenerateEvents(motion MotionData) []AnimationEvent
    Validate(animation Animation) QualityScore
}
```

## 7. CreativeAsset v2 新增字段

Animation 部分升级：

```json
{
  "animation": {
    "action": "attack",
    "frames": 10,
    "anchor": { "root": [256,490] },
    "motion": { "phases": ["prepare","strike","recover"] },
    "events": [ { "frame": 5, "type": "hit" } ]
  }
}
```

## 8. 技术壁垒

| 能力 | 升级内容 |
| ---- | -------- |
| Frame Alignment | 帧结构统一 |
| Root Alignment | 角色空间稳定 |
| Motion Understanding | 理解动作阶段 |
| Event Generation | 自动生成游戏事件 |

这已从图像处理升级为动画智能理解。

## 9. 合并位置（Merged Location）

| 概念 | Spec | 合并位置 |
| ---- | ---- | -------- |
| 帧抽取 / 锚点检测 / 运动相位 / 根运动纠偏 / 时序一致性 / 质量 | `motion_align/` | `falign/extraction/`、`falign/anchor/`、`falign/phase/`、`falign/motion/`、`falign/temporal/`、`falign/quality/`（`falign/pipeline` 串联） |
| MotionAlign 处理接口 | `motion_align/quality` | `adapters/creative_asset_adapter.py`（在 `CreativeAsset.animation.frames` 上运行对齐，回写 `quality.animation`） |
| 契约检查 | `tests/` | `tests/test_falign.md` |

见 [docs/architecture.md](../architecture.md) Layer 4（FAlign）。
