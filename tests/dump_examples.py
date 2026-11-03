"""Regenerates the JSON examples in examples/ from real pipeline runs.

Run from the repository root:

    python tests/dump_examples.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

EXAMPLES = os.path.join(ROOT, "examples")


def write(name, data):
    path = os.path.join(EXAMPLES, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, default=str)
    print("wrote examples/{}".format(name))


def make_frames():
    return [
        {
            "id": index,
            "image": "frame{}.png".format(index),
            "action": "walk",
            "anchor": {"root": {"x": 32 + index, "y": 60}, "feet": {"x": 32, "y": 64}},
        }
        for index in range(4)
    ]


def main():
    from agent.creative_agent import CreativeAgent
    from agents.supervisor.supervisor import SupervisorAgent
    from falign.pipeline.falign_engine import FAlignEngine
    from gimport.exporter.one_click_export import OneClickExporter
    from gimport.pipeline.gimport_engine import GImportEngine

    # Phase 4: FAlign over an AI-generated frame sequence
    write("animation_result.json", FAlignEngine().process(make_frames()))

    # Phase 5: GImport into Cocos + one-click package
    asset = {
        "id": "mage001",
        "name": "FireMage",
        "type": "character",
        "source": {"width": 64, "height": 64, "prompt": "pixel fire mage"},
        "animation": {"action": "walk", "fps": 12, "loop": True, "frames": make_frames()},
    }
    write("gimport_result.json", GImportEngine().process(asset, "cocos"))
    write("one_click_export.json", OneClickExporter().export(asset, "cocos"))

    # Phase 6: Creative Agent goal -> plan -> pipeline -> quality
    agent_result = CreativeAgent().run(
        "创建一个像素风RPG火焰法师角色，包含待机、攻击动画，并导入Cocos项目"
    )
    write(
        "agent_plan.json",
        {
            "goal": agent_result["goal"],
            "plan": agent_result["plan"],
            "quality": agent_result["quality"],
            "memory": agent_result["memory"],
        },
    )

    # Phase 7: Multi-Agent System end to end
    team_result = SupervisorAgent().run("生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")
    write(
        "multi_agent_result.json",
        {
            "goal": team_result["goal"],
            "plan": team_result["plan"],
            "supervisor": team_result["supervisor"],
            "messages": team_result["messages"],
            "asset": team_result["asset"],
        },
    )


if __name__ == "__main__":
    main()
