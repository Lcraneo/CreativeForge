# CreativeForge

Merged monorepo of the Phase 1–7 design packages. Each phase lives in its own
subtree; together they form one pipeline:

```text
User Goal
  -> Creative Agent / Multi-Agent System (Phase 6-7)
  -> CreativeAsset Contract (Phase 1)
  -> Windup Adapter (Phase 2)
  -> PReCon pixel reconstruction (Phase 3)
  -> FAlign frame alignment (Phase 4)
  -> GImport engine import (Phase 5)
  -> Cocos / Unity / Godot project
```

## Phase 1 — CreativeAsset Contract (frozen contract layer)

Version: CreativeAsset v1.0

- JSON Schema (`schemas/`)
- Core interfaces (`packages/creative-core/`)
- Adapter boundary definitions (`adapters/README.md`)
- Contract tests structure (`tests/contract/`)

## Phase 2 — Adapter Layer

Connects external capability projects (Holonic/Windup) with the CreativeAsset
Contract. External projects do not depend on CreativeForge core; all data
enters through the adapter boundary and outputs must be CreativeAsset
compatible.

- Holonic Adapter (`adapters/holonic/`)
- Windup Adapter (`adapters/windup/`)
- Adapter Registry (`core/registry.py`)
- Mapping Tests (`tests/test_adapter_contract.md`)

## Phase 3 — PReCon Engine

Self-developed pixel reconstruction engine (`precon/`):

```text
Input Image -> Grid Inference -> Semantic Palette Reconstruction
           -> Contour Repair -> Style Consistency -> Quality Evaluation
           -> CreativeAsset(pixel)
```

## Phase 4 — FAlign Engine

Self-developed frame alignment engine (`falign/`): automatic frame cutting,
alignment and correction for AI-generated game animation.

```text
Animation Frames -> Frame Extraction -> Anchor Detection
                 -> Motion Phase Alignment -> Root Motion Correction
                 -> Temporal Consistency -> Quality Evaluation
                 -> CreativeAsset(animation + quality.animation)
```

Solves: character drift (anchor alignment), foot sliding (root correction),
jitter (temporal consistency), broken action continuity (phase alignment).
Entry point: `falign.pipeline.falign_engine.FAlignEngine`; CreativeAsset
integration via `adapters/creative_asset_adapter.py`.

## Phase 5 — GImport Engine

Self-developed one-click engine import pipeline (`gimport/`):

```text
CreativeAsset -> Asset Manifest -> Sprite Atlas -> Animation Clip
              -> Prefab -> Engine Adapter -> Runtime Validation
              -> One Click Export
```

Multi-engine adapters (Cocos / Unity / Godot) turn one CreativeAsset into
engine-ready resources with automatic import validation. Entry points:
`gimport.pipeline.gimport_engine.GImportEngine`,
`gimport.exporter.one_click_export.OneClickExporter`.

## Phase 6 — Creative Agent

Goal-driven autonomous planning layer (`agent/`). The user describes the
final goal ("创建一个像素风RPG火焰法师角色，导入Cocos项目") and the agent
plans and runs the pipeline:

```text
Goal -> Intent Analyzer -> Planner -> Capability Router
     -> Workflow Executor -> Quality Gate -> (retry / fallback / human-in-loop)
     -> Output
```

Capabilities (generation / PReCon / FAlign / GImport) are registered, not
hardcoded; long tasks checkpoint into task memory and resume without re-running
completed steps. Entry point: `agent.creative_agent.CreativeAgent.run(goal)`.

## Phase 7 — Multi-Agent System

The agent layer becomes an AI game asset production team (`agents/` +
`protocol/`): a Supervisor Agent plans a task graph and dispatches specialist
agents over a message protocol.

```text
Supervisor Agent
  -> Art Agent (Generation + PReCon)
  -> Animation Agent (FAlign)
  -> Engine Agent (GImport: Unity / Cocos / Godot)
  -> QA Agent (validate -> repair round)
  -> Memory Agent (style / versions / checkpoints)
```

Entry point: `agents.supervisor.supervisor.SupervisorAgent.run(goal)`.

## Quickstart

```text
python tests/run_tests.py       # 36 contract checks across Phases 3-7
python tests/dump_examples.py   # regenerate examples/*.json from real runs
```

Programmatic demo:

```python
from agents.supervisor.supervisor import SupervisorAgent

result = SupervisorAgent().run("生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")
print(result["supervisor"]["status"])   # PASS
print(result["asset"]["engine"]["target"])  # unity
```

See `docs/architecture.md` for the full architecture and the phase spec ->
merged location mapping, and `examples/` for real pipeline outputs.
