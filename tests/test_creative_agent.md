# Creative Agent Contract Tests (Phase 6)

1. Intent analyzer detects target engine and static-image goals (no animation needed).
2. Planner emits capability-based task plans (generation / PReCon / FAlign / GImport).
3. Capability registry resolves planner capabilities to handlers.
4. Task executor raises on unknown capabilities.
5. Task memory stores goal, plan, checkpoints, asset versions and errors.
6. Quality gate flags sections below threshold for retry.
7. Recovery manager retries, falls back (Unity -> Cocos) and escalates to human-in-loop.
8. Workflow engine runs plans to completion and resumes from checkpoints without re-running completed tasks.
9. CreativeAgent.run returns plan + workflow + asset + quality + memory.

Future:
- LLM-backed intent analysis and planning
- parallel task graph execution
- persistent memory backend
