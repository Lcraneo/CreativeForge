"""Agent Planner (Phase 11.7 / Phase 14.11 / Phase 15.4).

Turns a natural language goal into an ordered capability task list. Rule
based in the MVP; swap in an LLM planner (LangGraph) later — the output
contract stays `{"goal", "mode", "tasks", "engine"}`.
"""

CREATE_KEYWORDS = ("创建", "生成", "做一个", "制作")
MODIFY_KEYWORDS = ("修改", "换成", "换一", "换把", "增加", "加一", "加把", "升级", "改造", "替换", "给")

CREATE_TASKS = [
    "generate_asset",
    "structure_asset",
    "create_dna",
    "motion_align",
    "gimport",
]

MODIFY_TASKS = [
    "find_character",
    *CREATE_TASKS,
]

ENGINE_KEYWORDS = (("unity", "unity"), ("cocos", "cocos"), ("godot", "godot"))


def detect_engine(goal: str) -> str | None:
    lowered = (goal or "").lower()
    for keyword, engine in ENGINE_KEYWORDS:
        if keyword in lowered:
            return engine
    return None


class Planner:
    def create_plan(self, goal: str) -> dict:
        if any(keyword in goal for keyword in MODIFY_KEYWORDS) and not any(
            keyword in goal for keyword in CREATE_KEYWORDS
        ):
            # Phase 14: modification keeps identity, never regenerates it.
            mode, tasks = "modify_existing_character", list(MODIFY_TASKS)
        else:
            mode, tasks = "create_character", list(CREATE_TASKS)
        return {"goal": goal, "mode": mode, "tasks": tasks, "engine": detect_engine(goal)}


planner = Planner()
