# CreativeForge

Merged monorepo of Phase 1–3 design packages. Each phase lives in its own
subtree; together they form the CreativeForge architecture.

## Phase 1 — CreativeAsset Contract (frozen contract layer)

Version: CreativeAsset v1.0

This package contains the frozen contract layer design:

- JSON Schema (`schemas/`)
- Core interfaces (`packages/creative-core/`)
- Adapter boundary definitions (`adapters/README.md`)
- Contract tests structure (`tests/contract/`)

Next phases:
1. Holonic Adapter
2. Windup Adapter
3. PReCon Engine
4. FAlign Engine
5. GImport Engine

## Phase 2 — Adapter Layer

Purpose:
Connect external capability projects (Holonic/Windup) with CreativeAsset Contract.

Design principles:
1. External projects do not depend on CreativeForge core.
2. All data enters through Adapter boundary.
3. Output must be CreativeAsset compatible.

Modules:
- Holonic Adapter (`adapters/holonic/`)
- Windup Adapter (`adapters/windup/`)
- Adapter Registry (`core/registry.py`)
- Mapping Tests (`tests/test_adapter_contract.md`)

## Phase 3 — PReCon Engine

Self-developed pixel reconstruction engine design.

Pipeline:

```
Input Image
 -> Grid Inference
 -> Semantic Palette Reconstruction
 -> Contour Repair
 -> Style Consistency
 -> Quality Evaluation
 -> CreativeAsset(pixel)
```

This phase implements the architecture skeleton (`precon/`).
