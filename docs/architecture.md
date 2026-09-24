# CreativeForge Architecture

CreativeForge turns a natural-language goal into engine-ready game assets:

```text
                 User Goal

                     |
                     v

              Creative Agent            (Phase 6)
              Multi-Agent System        (Phase 7)

                     |
                     v

            CreativeAsset Contract      (Phase 1)

                     |
                     v

  ---------------------------------------------------------
  Windup Adapter     PReCon        FAlign        GImport
  (Phase 2)         (Phase 3)     (Phase 4)     (Phase 5)
  generation        pixel          animation     engine
                    reconstruction alignment    import
  ---------------------------------------------------------

                     |
                     v

             Game Engine Project (Cocos / Unity / Godot)
```

## Layer 1 — CreativeAsset Contract (frozen contract)

- JSON Schema: `schemas/` (creative_asset / pixel / animation)
- Core interfaces: `packages/creative-core/`
- Adapter boundary: `adapters/README.md`
- Contract tests: `tests/contract/`

Every engine and agent reads and writes CreativeAsset; nothing bypasses the
contract.

## Layer 2 — Adapter Layer

External capability projects (Holonic / Windup) enter only through adapters:

- `adapters/holonic/` — asset / image / video / task mappers
- `adapters/windup/` — generation / pixel / animation / cocos mappers
- `core/registry.py` — adapter registry
- `core/adapter.py` — `AssetAdapter` interface (name / version / can_handle /
  import_asset / export_asset)

## Layer 3 — PReCon Engine (pixel reconstruction)

`precon/` — self-developed pixel reconstruction:

```text
Input Image -> Grid Inference -> Semantic Palette Reconstruction
           -> Contour Repair -> Style Consistency -> Quality Evaluation
           -> CreativeAsset(pixel + quality.pixel)
```

## Layer 4 — FAlign Engine (frame alignment)

`falign/` — AI 游戏动画生成后的自动切帧、对齐、纠偏引擎：

| Problem | Cause | FAlign handling |
| ------- | ----- | --------------- |
| 人物漂移 | 每帧主体位置变化 | Anchor Alignment |
| 脚底滑动 | Root Motion 不稳定 | Root Correction |
| 动作抖动 | 帧间差异过大 | Temporal Consistency |
| 动作不连贯 | 动作阶段错位 | Motion Phase Alignment |

```text
Animation Frames -> Frame Extraction -> Anchor Detection
                 -> Motion Phase Alignment -> Root Motion Correction
                 -> Temporal Consistency -> Quality Evaluation
                 -> CreativeAsset(animation + quality.animation)
```

Modules:

- `falign/extraction/frame_extractor.py` — normalizes sprite sheet / video /
  gif / AI sequence input into id + image frames
- `falign/anchor/anchor_detector.py` — stable keypoints per frame
  (root / feet / center / head)
- `falign/phase/phase_alignment.py` — maps frames onto the canonical motion
  phase track (0 / 0.25 / 0.5 / 0.75 / 1)
- `falign/motion/root_motion.py` — classifies root deltas as real motion or
  drift; drift is corrected back to the frame-0 root
- `falign/temporal/temporal_consistency.py` — adjacent-frame difference ->
  jitter score + smooth verdict
- `falign/quality/animation_quality.py` — anchor / motion / temporal / overall
  scores written to `quality.animation`
- `adapters/creative_asset_adapter.py` — runs FAlign over
  `CreativeAsset.animation.frames` and writes results back

## Layer 5 — GImport Engine (one-click engine import)

`gimport/` — AI 生成资产到游戏引擎项目的一键编译导入系统：

```text
CreativeAsset -> Asset Manifest -> Sprite Atlas -> Animation Clip
              -> Prefab -> Engine Adapter -> Runtime Validation
              -> One Click Export
```

Modules:

- `gimport/manifest/` — asset manifest (the asset's engine ID card) + schema
  validation
- `gimport/atlas/sprite_atlas_builder.py` — packs frames into one atlas
  (fewer draw calls)
- `gimport/animation/animation_clip_generator.py` — Unity clip (fps / loop) or
  Cocos animation (duration / sample) from the FAlign-aligned state
- `gimport/prefab/prefab_generator.py` — character entity with
  SpriteRenderer / Animator / Collider / Script / AnimationController
- `gimport/adapters/` — `EngineAdapter` interface + Cocos / Unity / Godot
  adapters (same asset, multiple engines)
- `gimport/validation/runtime_validator.py` — resource integrity, animation
  integrity, engine compatibility -> status + score
- `gimport/exporter/one_click_export.py` — goal to shareable engine package

## Layer 6 — Creative Agent (planning + orchestration)

`agent/` — 从「AI 工具链」升级为「自主规划型 AI 游戏资产生产 Agent」：

```text
User Goal -> Intent Analyzer -> Planner -> Capability Router -> Workflow
          Executor (PReCon / FAlign / GImport) -> Quality Gate -> Output
```

Modules:

- `agent/planner/intent_analyzer.py` — engine, style, static-vs-animated
- `agent/planner/planner.py` — goal -> capability-based task plan
- `agent/capability/capability_registry.py` — capabilities (name / type /
  input / output / cost / quality) bound to the Phase 3-5 engines
- `agent/executor/task_executor.py` — task -> capability -> handler
- `agent/memory/task_memory.py` — goal, plan, checkpoints, asset versions,
  errors (CreativeAsset as evolving state)
- `agent/monitor/quality_gate.py` — unified quality thresholds
  (pixel 0.8 / animation 0.85 / engine 0.9), flags retry
- `agent/recovery/recovery_manager.py` — retry -> fallback (Unity -> Cocos)
  -> human-in-loop
- `agent/workflow/workflow_engine.py` — node/edge/state execution with
  checkpoint resume (LangGraph / Temporal style)
- `agent/creative_agent.py` — `CreativeAgent.run(goal)` entry point

## Layer 7 — Multi-Agent System

`agents/` + `protocol/` — CreativeForge AI 游戏资产生产团队：

```text
                User Goal
                    |
                    v
             Supervisor Agent        agents/supervisor/
             (planner + router + QA/repair loop + memory)
                    |
    +---------------+----------------+
    |               |                |
    v               v                v
 Art Agent    Animation Agent   Engine Agent
 (Generation   (FAlign)          (GImport)
  + PReCon)
    \               |                /
     +--------------+---------------+
                    v
                QA Agent              agents/qa_agent/
                    v
              Memory Agent             agents/memory_agent/
```

Modules:

- `protocol/message.py` — `AgentMessage` (from / to / type / payload) +
  `MessageBus` (TASK_ASSIGN / TASK_RESULT / ASSET_READY / QUALITY_REPORT /
  RECOVERY_REQUEST)
- `protocol/state.py` — agent lifecycle CREATED -> RUNNING -> SUCCESS / FAILED
  / RECOVERY
- `agents/base_agent.py` — named, stateful, fixed action set
- `agents/supervisor/planner.py` — goal -> task graph with agent assignments
  (reuses the Phase 6 intent analyzer)
- `agents/supervisor/task_router.py` — dispatch to registered agents
- `agents/supervisor/supervisor.py` — the brain: executes the task graph,
  hands assets off via ASSET_READY, runs QA, performs one repair round on
  RETRY, checkpoints via the Memory Agent
- `agents/art_agent/`, `agents/animation_agent/`, `agents/engine_agent/` —
  specialists delegating to the shared capability registry
- `agents/qa_agent/` — generate -> validate -> repair loop (pixel / animation
  / engine sections)
- `agents/memory_agent/` — user style, asset versions, task history,
  checkpoints (keeps style consistent across tasks)

## Phase spec -> merged location mapping

The original phase packages were standalone; the merged repo consolidates
them:

| Phase | Spec location | Merged location |
| ----- | ------------- | --------------- |
| 4 | `falign/` (standalone package) | `falign/` (same layout) |
| 4 | `adapters/creative_asset_adapter.py` | same |
| 5 | `gimport/` (standalone package) | `gimport/` (same layout; adapters under `gimport/adapters/`) |
| 6 | `planner/ executor/ memory/ capability/ workflow/ monitor/ recovery/` | `agent/planner/ agent/executor/ agent/memory/ agent/capability/ agent/workflow/ agent/monitor/ agent/recovery/` + `agent/creative_agent.py` |
| 7 | `agents/` + `protocol/` + `workflow/` + `registry/` | `agents/` + `protocol/`; workflow execution and checkpointing reuse `agent/workflow/` + `agent/memory/`; capability registry reused from `agent/capability/` (agents bind via `Capability.agent`) |

## Verification

```text
python tests/run_tests.py      # 36 contract checks (Phases 3-7)
python tests/dump_examples.py  # regenerate examples/*.json from real runs
```

Contract docs: `tests/test_precon.md`, `tests/test_adapter_contract.md`,
`tests/test_falign.md`, `tests/test_gimport.md`,
`tests/test_creative_agent.md`, `tests/agent_test.md`.
