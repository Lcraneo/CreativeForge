"""Animation Graph (Phase 15.3.12): states as a graph, not a list."""

from typing import Any

from app.engines.motion_align.timeline.state_machine import AnimationState


class AnimationGraph:
    def build(self, states: list[AnimationState]) -> dict[str, Any]:
        return {
            "nodes": [state.name for state in states],
            "edges": [
                {"from": state.name, "to": transition.to, "condition": transition.condition}
                for state in states
                for transition in state.transitions
            ],
        }
