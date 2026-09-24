# Multi-Agent System Contract Tests (Phase 7)

1. AgentMessage serializes from / to / type / payload; MessageBus routes per agent.
2. Agent state machine walks CREATED -> RUNNING -> SUCCESS and rejects invalid states.
3. Supervisor planner assigns ArtAgent / AnimationAgent / EngineAgent tasks from the goal.
4. Task router dispatches to registered agents and rejects unknown agents / actions.
5. ArtAgent runs Generation -> PReCon; AnimationAgent runs FAlign; EngineAgent runs GImport per engine.
6. QA Agent produces the unified quality report (pixel / animation / engine).
7. Supervisor hands off assets between agents via ASSET_READY messages.
8. Supervisor runs QA, one repair round on RETRY, then Memory checkpoint.
9. End-to-end: goal -> plan -> agents -> quality -> memory -> engine-ready asset.

Future:
- parallel agent execution
- agent-level negotiation (style conflicts)
- persistent memory across sessions
