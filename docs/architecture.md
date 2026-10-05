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

## Layer 8 — CreativeForge Studio (product platform, Phase 8)

`studio/` — the product layer: an AI asset factory console.

```text
frontend (React 18 + TS + Vite)
  Workspace -> Agent Command Center (React Flow task graph)
            -> Asset Inspector (R3F 3D viewer) -> Pixel Studio (Konva)
            -> Animation Studio -> Benchmark Center -> Export Center
  Zustand stores + WebSocket event stream (staggered replay)

backend (FastAPI)
  POST /api/tasks            create a production task (202 + stream_url)
  GET  /api/tasks/{id}       plan / events / supervisor record
  WS   /ws/tasks/{id}/stream PLAN_CREATED | AGENT_START | AGENT_DONE |
                            QUALITY_REPORT | TASK_COMPLETE | ASSET_UPDATE
  GET  /api/assets/{id}      CreativeAsset
  POST /api/export           real zip engine package (download_url)
  GET  /api/benchmark        live Phase 9 evaluation
```

- `studio/backend/agent_runtime/runtime.py` — runs the Supervisor in a
  background thread and streams lifecycle events into the task store
- `studio/backend/export_service/service.py` — CreativeAsset -> real zip
  (Character / Animation / Prefab / Config), served for download
- entry: `python -m studio.backend.main` (also serves `studio/frontend/dist`)

## Layer 9 — Benchmark System (Phase 9)

`benchmark/` — proves the self-developed layer with data:

```text
Dataset (12 assets / 6 categories)
  -> PReCon metrics   PCS / palette efficiency / contour accuracy
                     vs naive pixelate baseline
  -> FAlign metrics   root drift / foot sliding / temporal smoothness
                     vs raw AI frames baseline
  -> GImport metrics  ISR / pipeline time / manual steps vs 12-step manual
  -> Agent metrics    completion / planning accuracy / recovery / time
  -> CF Score         weighted (pixel .3 / animation .3 / engine .25 / agent .15)
```

Entry: `python -m benchmark.run_benchmark` — writes
`benchmark/results/benchmark_report.{json,md}` with the real engines.

## Layer 10 — Release & Demo (Phase 10)

- `examples/competition_demo/run_demo.py` — the fixed, deterministic
  competition demo: goal -> source/ (intent + task graph) ->
  intermediate/ (steps + messages + asset) -> output/ (real zip) ->
  report/ (quality + benchmark summary)
- `tests/release/run_release_tests.py` — four-layer release validation:
  L1 Contract / L2 Pipeline / L3 Runtime (exported zip opens, clip plays,
  prefab wires) / L4 Performance (timings, memory, thresholds)
- `docker-compose.yml` + `docker/Dockerfile` — one-command deployment

## Layer 11 — CreativeForge Backend (Phase 11-15)

`backend/` — the real extensible service (Phase 11-15 framework, not a
throwaway demo):

```text
User Prompt
   -> FastAPI            app/api/            create / list / dna / tasks
   -> Agent Planner      app/agent/          create vs modify plan + engine target
   -> Tool Router        app/agent/router.py ordered tools over one context
   -> Tools              app/tools/          generate / find_character / structure
                                             / dna / motion_align / gimport
   -> Adapter Layer      app/adapters/       Windup (real client or mock) -> CreativeAsset
   -> Engines            app/engines/        asset_struct / character_dna
                                             / motion_align / gimport (Phase 13-15)
   -> CreativeAsset v1   (frozen contract, enriched step by step)
   -> PostgreSQL         app/models/         assets, asset_layers, asset_nodes,
                                             character_dnas, character_embeddings,
                                             character_versions, animation_clips,
                                             animation_events, tasks
```

- `app/core/` — settings (`.env`) + async SQLAlchemy engine (`get_db`)
- `app/models/` — Phase 11 (asset, task) + Phase 13 (asset_layers,
  asset_nodes) + Phase 14 (character_dnas, character_embeddings,
  character_versions) + Phase 15 (animation_clips, animation_events,
  animation_states)
- `app/tools/` — `BaseTool` plugin + `ToolRegistry`; the 6 pipeline tools
  hand the evolving CreativeAsset through one shared context
- `app/adapters/` — `AssetAdapter` interface; `WINDUP_BASE_URL` unset runs
  the deterministic mock client, set it to hit the real generation API
- `app/engines/motion_align/alignment/anchor_solver.py` — Phase 15.1 core:
  mean-root translation + scale normalization + rotation alignment, all
  about the shared root (residual < 1 px)
- `app/engines/gimport/` — `EngineExporter` interface + Cocos / Unity
  exporters + `GImportProcessor` (engine target from prompt)
- modification flow (Phase 14.11): `find_character` -> identity-preserving
  generation (`..._v2.png`) -> cosine similarity > 0.85 -> version row

## Layer 12 — Agent Runtime (Phase 16-17)

`backend/app/runtime/` — the backend stops being a fixed tool chain and
becomes an autonomous production system: the user states a goal, the
agents decide which modules run, in what order, and how to recover.

```text
User Goal
   -> Intent Analyzer     runtime/intent.py     type / engine / style / requirements
   -> Planner Runtime     runtime/planner.py    dynamic decisions -> DAG plan
   -> Agent Executor      runtime/executor.py   drives the DAG with checkpoints
        |   (parallel branches)   AssetStructAgent -> {DNAAgent // MotionAgent}
        v                          -> CombatAgent -> ExportAgent -> QualityAgent
   -> Quality Gate        runtime/agents/quality.py  structural / dna / motion / runtime
   -> Self Healing        runtime/healing.py    rerun offenders once, then fail loud
   -> Human Review        runtime/review.py     WAITING_REVIEW -> approve -> resume
   -> Memory              runtime/memory.py     preferences (DB) + process stats
   -> Asset Git           runtime/versions.py   version lineage trees
```

- MCP-style tool schemas (`runtime/registry.py`) let the Planner do
  capability matching instead of hard-coded flows
- state machine: CREATED -> PLANNING -> RUNNING -> WAITING_REVIEW?
  -> COMPLETED | FAILED (every step committed to `agent_tasks`)
- checkpointing: the shared context snapshot lives in
  `agent_tasks.checkpoint`; approval resumes without redoing completed
  nodes (Phase 17.7)
- parallel branches run session-free (`_invoke_agent` never touches the
  AsyncSession) — concurrency-safe by construction

## Layer 13 — Foundation Models (Phase 19)

`backend/app/engines/foundation/` — the model layer behind the DNA and
quality systems (deterministic stand-ins behind frozen interfaces):

- `dna_profiles.py` — six-layer Character DNA: Appearance / Style /
  Structure / Equipment / Motion / Combat (Phase 19.4)
- `quality_model.py` — identity consistency scoring: appearance palette
  overlap + structure deviation + style match (Phase 19.12)
- `animation_library.py` — animation knowledge base with semantics and
  difficulty per action; the Motion Agent resolves actions from it
  (Phase 19.11)

Training-data loops and the graph database (Neo4j asset graph) remain
design-only per the phase spec; the interfaces above are where the
trained models plug in.

## Layer 14 — Model Training & Deployment (Phase 20)

`backend/app/engines/foundation/training/` — the asset library becomes a
training corpus: the first trained component of CreativeForge, still
deterministic end to end.

```text
POST /api/v1/models/train
   -> Dataset      dataset.py      same character across versions/views ->
                                   positive pairs, cross character -> negative
   -> Preprocess   quality filter  engine manifest score < 1.0 dropped
   -> Features     encoder.py      DINOv2+CLIP stand-ins: 32 identity dims
                                   + 32 nuisance dims (view noise)
   -> Training     trainer.py      contrastive loss (margin), real gradient
                                   descent on a diagonal projection head, no RNG
   -> Evaluation   evaluation.py   positive/negative cosine, margin,
                                   retrieval@1 — before vs after
   -> Registry     registry.py     staged -> production -> archived
                                   (model_artifacts + training_runs tables)
   -> Serving      model_service.py  /models/dna/embed runs the production
                                     projection through the GPU queue
```

Measured on a two-character corpus (3 images x 3 views): positive cosine
0.684 -> 0.978, margin 0.671 -> 0.843, loss 1.83 -> 0.009 in <0.2s. Swapping
the hash backbones for real DINOv2/CLIP forward passes only touches
`encoder.py`; training, registry and serving stay untouched.

Task tiers (spec 十七): every executor step records `tier` (gpu = image
generation / animation analysis / model inference; cpu = planning /
metadata / graph), and `runtime/tiers.py` `GpuQueue` is the single-worker
stand-in for the GPU worker pool.

## Layer 15 — Product MVP (Phase 21)

> **已删除（2026-10-05）**：本层的 `frontend/`（MVP 三页）与配套旧后端 `backend/`
> 已按 `docs/legacy-inventory.md` M3 计划整体删除，studio 是唯一正式产品面。
> 下文保留为 phase 设计记录。

`frontend/` — the three MVP pages from the phase spec, React 18 + Vite +
Tailwind 4, talking to the backend through `/api` (dev/preview proxy to
:8765):

```text
Creation Studio   prompt + engine/style params -> POST /assets/create
                  -> auto-advances to the timeline on completion
Agent Timeline    DAG layered view (✓/⟳/○ per node, GPU/CPU tier badges,
                  ms timings) + execution trace + planner decisions
                  + WAITING_REVIEW approve + task history
Asset Viewer      six-layer DNA profile / layers / palette / animation
                  clips / combat skills / engine export (file tree +
                  quality scores) + zip download
```

Backend export loop: `GET /api/v1/assets/{id}/export.zip?engine=cocos`
packages the engine resource tree into a real archive — DNA.json,
skill.json, collider.json, textures (stdlib placeholder PNG),
spriteframes, animations, prefab. Verified in-browser end to end:
prompt -> DAG timeline -> asset inspector -> cocos zip.

## Layer 16 — Advanced Agent Platform (Phase 22)

The runtime stops being a fixed pipeline: the plan itself becomes
change-aware.

- **Dynamic Planner** — `intent.change` classifies edits (style / weapon /
  motion / full). A style edit plans the minimal chain
  `find_character -> modify_style -> quality_check`: the new **StyleAgent**
  recolors the palette on the latest version and inherits the previous
  version's layers / animation / combat / engine payload whole (found via
  the **Asset Context Retriever**, which loads the character's newest full
  asset into `context["previous_asset"]`). Weapon and motion edits keep
  the full identity-preserving pipeline. Skipped stages are recorded as
  planner decisions.
- **Self Evaluation** — every step summary carries a deterministic
  `confidence` (`runtime/evaluation.py`: segmentation score, motion
  residual, manifest score, ...). Nodes below `CONFIDENCE_FLOOR` (0.8)
  rerun once through a `self_evaluation` healing step, then fail loud.
- **MCP Tool Ecosystem** — `GET /api/v1/mcp/tools` publishes the manifest
  (planner pipeline tools + standalone `export_*` / `dna_embed` /
  `asset_quality` / `motion_analyze` / `train_dna_encoder`), and
  `POST /api/v1/mcp/invoke` executes the standalone ones.
- **Collaboration + Tenancy** — `projects` / `project_members`
  (owner / reviewer / developer / designer) with a role-guarded asset
  lifecycle `submit -> in_review -> approve -> approved -> promote ->
  production` (403 on wrong role, 409 on wrong state), and `tenant_id`
  scoping for the SaaS split.

## Layer 17 — Research & Innovation (Phase 23)

The system starts to reason about relations, rules and gameplay —
Game Creation Intelligence on deterministic stand-ins behind frozen
interfaces:

```text
Knowledge Layer    foundation/knowledge.py    Character --HAS_WEAPON--> Weapon
                                              --TRIGGERS--> Skill --NEEDS--> Animation
                                              (+ HAS_SKILL / HAS_STYLE / EXPORTED_TO)
                   KnowledgeRetriever         relation facts + DNA metadata ->
                                              context pack for the agents
                                              (GET /api/v1/knowledge/graph)
Logic Layer        foundation/game_logic.py   CreativeSkill blueprint: goal ->
                                              skill type + element -> numbers
                                              -> Cocos events + Unity C# script
                                              ("dash" matches the spec example
                                              exactly: 20 dmg / cd 3 / blue_flash)
Simulation Layer   foundation/simulation.py   physics / gameplay / performance
                                              checks; overpowered values are
                                              auto-repaired (fireball 87.5 -> 80)
                                              with before/after records
Evaluation Layer   runtime/evaluation.py      every task ships with an
                                              evaluation {identity, animation,
                                              engine} -> feedback loop data point
Benchmark          foundation/benchmark.py    Asset / Game / Agent planes ->
                                              CF Game Score
                                              (POST /api/v1/benchmark/run)
```

Dynamic Planner grows a third minimal chain: `change=skill` runs
`find_character -> create_logic -> simulate -> gimport -> quality_check`
(new logic, no artwork regeneration, engine package re-exported). A
`build_dag` fix connects head to tail on linear chains — short chains
previously left `quality_check` disconnected.

## Phase spec -> merged location mapping

The original phase packages were standalone; the merged repo consolidates
them. Design/decision records live in `docs/phases/` (see
[docs/phases/README.md](phases/README.md)); the table below maps every phase
spec (original design numbering) to its final implementation location. Note:
the inline `(Phase N)` tags in the overview diagram and Layer headings above
use the *consolidated* layer numbering, while `docs/phases/phaseN.md` keep
the *original* 10-step design numbering — the table reconciles the two.

| Phase | Spec location | Merged location |
| ----- | ------------- | --------------- |
| 1 | `docs/phases/phase1.md` | `schemas/` + `packages/creative-core/` + `core/adapter.py`、`core/registry.py` |
| 2 | `docs/phases/phase2.md` | `adapters/windup/`、`adapters/holonic/`、`adapters/creative_asset_adapter.py` + `docs/mapping/` |
| 3 | `docs/phases/phase3.md` | `precon/`（grid/palette/contour/style/pipeline/quality）；图层/Anchor/Metadata 下沉到 `gimport/manifest`、`gimport/prefab` |
| 4 | `docs/phases/phase4.md` | `precon/style/` + `agent/memory/task_memory.py` + `agents/memory_agent/` |
| 5 | `docs/phases/phase5.md` | `falign/`（extraction/anchor/phase/motion/temporal/quality/pipeline） |
| 6 | `docs/phases/phase6.md` | `gimport/atlas/`、`gimport/animation/`、`gimport/prefab/`、`gimport/manifest/` |
| 7 | `docs/phases/phase7.md` | `gimport/adapters/`、`gimport/validation/`、`gimport/exporter/`、`gimport/pipeline/` |
| 8 | `docs/phases/phase8.md` | `agent/`（planner/executor/memory/capability/workflow/monitor/recovery + `creative_agent.py`）+ `agents/` + `protocol/` + `studio/` |
| 9 | `docs/phases/phase9.md` | `benchmark/`（dataset/metrics/score/run_benchmark） |
| 10 | `docs/phases/phase10.md` | `examples/competition_demo/` + `tests/release/` + `docker-compose.yml` + `docker/` + `studio/` |
| 11 | `docs/phases/phase11.md` | `backend/`（app/core、app/models、app/agent、app/tools、app/services、app/api、app/main.py） |
| 12 | `docs/phases/phase12.md` | `backend/app/adapters/`（base / windup/{client,mapper,adapter} / holonic / registry） |
| 13 | `docs/phases/phase13.md` | `backend/app/engines/asset_struct/`（analyzer/segmentation/layers/graph/builder/processor）+ `backend/app/models/asset_struct.py` |
| 14 | `docs/phases/phase14.md` | `backend/app/engines/character_dna/`（encoder/vector/retrieval/memory/version/service）+ `backend/app/models/character_dna.py` + `backend/app/api/dna.py` |
| 15 | `docs/phases/phase15.md` | `backend/app/engines/motion_align/`（models/detector/alignment/extraction/sprite/timeline/collision/exporter/pipeline）+ `backend/app/engines/gimport/` + `backend/app/models/animation.py` |
| 16 | `docs/phases/phase16.md` | `backend/app/runtime/`（intent / planner / graph / agents/{generate,struct,dna,motion,combat,export,quality} / registry） |
| 17 | `docs/phases/phase17.md` | `backend/app/runtime/`（executor / gateway / memory / versions / review / healing）+ `backend/app/models/runtime.py` |
| 18 | `docs/phases/phase18.md` | `backend/app/api/`（任务轨迹 / approve / export）+ `backend/app/schemas/` + `backend/app/services/asset_service.py`（Runtime 接入） |
| 19 | `docs/phases/phase19.md` | `backend/app/engines/foundation/`（dna_profiles / quality_model / animation_library）+ DNA service profile 接入 |
| 20 | `docs/phases/phase20.md` | `backend/app/engines/foundation/training/`（dataset / encoder / trainer / evaluation / pipeline / registry）+ `backend/app/models/training.py` + `backend/app/api/models.py` + `backend/app/services/model_service.py` + `backend/app/runtime/tiers.py` |
| 21 | `docs/phases/phase21.md` | `frontend/`（Creation Studio / Agent Timeline / Asset Viewer）+ `backend/app/api/asset.py`（export.zip）+ `backend/app/services/export_service.py` |
| 22 | `docs/phases/phase22.md` | `backend/app/runtime/`（planner / intent / evaluation / `agents/style.py`）+ `backend/app/tools/style_tool.py` + `backend/app/api/mcp.py` + `backend/app/api/collab.py` + `backend/app/models/collab.py` |
| 23 | `docs/phases/phase23.md` | `backend/app/engines/foundation/`（knowledge / game_logic / simulation / benchmark）+ `backend/app/runtime/agents/{logic,simulate}.py` + `backend/app/tools/{logic,simulate}_tool.py` + `backend/app/api/{knowledge,benchmark}.py` |

## Verification

```text
python tests/run_tests.py                  # 36 contract checks (Phases 3-7)
python tests/release/run_release_tests.py  # 12 release checks (4 layers, Phase 10)
python -m benchmark.run_benchmark          # Phase 9 evaluation report
python tests/dump_examples.py              # regenerate examples/*.json from real runs
python backend/tests/run_backend_tests.py  # 40 backend E2E checks (Phases 11-15)
python backend/tests/run_runtime_tests.py  # 36 agent runtime checks (Phases 16-19)
python backend/tests/run_training_tests.py  # 30 training pipeline checks (Phase 20)
python backend/tests/run_phase21_tests.py  # 19 export-zip / product checks (Phase 21)
python backend/tests/run_phase22_tests.py  # 34 dynamic-planner / mcp / collab checks (Phase 22)
python backend/tests/run_phase23_tests.py  # 25 knowledge / game-logic / simulation checks (Phase 23)
```

Contract docs: `tests/test_precon.md`, `tests/test_adapter_contract.md`,
`tests/test_falign.md`, `tests/test_gimport.md`,
`tests/test_creative_agent.md`, `tests/agent_test.md`.
