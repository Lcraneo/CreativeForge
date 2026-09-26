"""Animation State Machine (Phase 15.3.4-6): characters switch states,
they do not play single clips.

    Idle --move--> Run --attack--> Attack --(end)--> Idle
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StateTransition:
    condition: str
    to: str


@dataclass
class AnimationState:
    name: str
    clip: str
    loop: bool = True
    transitions: list[StateTransition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "clip": self.clip,
            "loop": self.loop,
            "transitions": [
                {"condition": t.condition, "to": t.to} for t in self.transitions
            ],
        }


def default_states(clip_name: str = "idle") -> list[AnimationState]:
    idle = AnimationState("idle", "idle", loop=True, transitions=[StateTransition("move", "run"), StateTransition("attack", "attack")])
    run = AnimationState("run", "run", loop=True, transitions=[StateTransition("attack", "attack"), StateTransition("idle", "idle")])
    attack = AnimationState("attack", "attack", loop=False, transitions=[StateTransition("end", "idle")])
    if clip_name == "idle":
        return [idle, run, attack]
    return [idle, run, attack]


class AnimationStateMachine:
    def __init__(self, states: list[AnimationState], initial: str = "idle"):
        self.states = {state.name: state for state in states}
        self.current = self.states.get(initial, states[0])

    def next(self, inputs: dict[str, Any]) -> AnimationState:
        for transition in self.current.transitions:
            if inputs.get(transition.condition):
                self.current = self.states[transition.to]
                break
        return self.current

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial": "idle",
            "current": self.current.name,
            "states": [state.to_dict() for state in self.states.values()],
        }
