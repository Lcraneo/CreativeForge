"""Phase 10 Mode A: the fixed competition demo.

    python examples/competition_demo/run_demo.py [--engine unity]

Demo Case 001 — Pixel RPG Boss Creation:

    创建一个像素RPG火焰法师Boss，带攻击动画，并导入Unity

Runs the real Multi-Agent pipeline once, deterministically, and freezes the
full evidence chain on disk:

    examples/competition_demo/
    ├── prompt.txt            the user goal
    ├── source/               intent + plan (what the Supervisor decided)
    ├── intermediate/         per-step agent records + messages
    ├── output/               the exported engine package (real zip)
    └── report/               quality report + benchmark summary

Nothing here is randomized: same goal in, same artifact out, every run.
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEMO_GOAL = "创建一个像素RPG火焰法师Boss，带攻击动画，并导入Unity"

from agents.supervisor.supervisor import SupervisorAgent  # noqa: E402


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def main():
    parser = argparse.ArgumentParser(description="CreativeForge competition demo")
    parser.add_argument("--engine", default="unity", choices=("unity", "cocos", "godot"))
    args = parser.parse_args()

    goal = DEMO_GOAL.replace("导入Unity", "导入{}".format(args.engine.capitalize()))
    base = os.path.dirname(os.path.abspath(__file__))
    for folder in ("source", "intermediate", "output", "report"):
        os.makedirs(os.path.join(base, folder), exist_ok=True)

    write_text(os.path.join(base, "prompt.txt"), goal + "\n")

    print("== CreativeForge Competition Demo ==")
    print("goal: {}".format(goal))

    result = SupervisorAgent().run(goal)

    write_json(os.path.join(base, "source", "intent.json"),
               result["plan"]["intent"])
    write_json(os.path.join(base, "source", "task_graph.json"),
               result["plan"]["tasks"])
    write_json(os.path.join(base, "intermediate", "supervisor_steps.json"),
               result["supervisor"]["steps"])
    write_json(os.path.join(base, "intermediate", "agent_messages.json"),
               result["messages"])

    asset = result["asset"]
    if asset is None:
        print("demo failed: supervisor returned no asset")
        return 1

    write_json(os.path.join(base, "intermediate", "creative_asset.json"), asset)

    from studio.backend.export_service.service import ExportService

    export = ExportService(os.path.join(base, "output")).export(asset, args.engine)
    write_json(os.path.join(base, "output", "export_summary.json"),
               {key: export[key] for key in
                ("package", "engine", "asset_id", "contents", "files",
                 "size_bytes", "validation")})

    quality = asset.get("quality", {})
    write_json(os.path.join(base, "report", "quality_report.json"), quality)

    from benchmark.evaluation import EvaluationReport

    benchmark = EvaluationReport().run()
    write_json(os.path.join(base, "report", "benchmark_summary.json"), {
        "precon": {key: benchmark["precon"][key] for key in
                   ("baseline_pixel_score", "method_pixel_score", "improvement")},
        "falign": {key: benchmark["falign"][key] for key in
                   ("baseline_root_drift", "method_root_drift", "drift_reduction")},
        "gimport": {key: benchmark["gimport"][key] for key in
                    ("import_success_rate",)},
        "agent": {key: benchmark["agent"][key] for key in
                  ("task_completion_rate", "planning_accuracy",
                   "recovery_success_rate")},
        "cf_score": benchmark["cf_score"]
    })

    print("status: {}".format(result["supervisor"]["status"]))
    print("asset : {} ({}) -> {}".format(
        asset["id"], asset.get("name"), export["package"]))
    print("quality: {}".format(quality.get("report", {}).get("status")))
    print("demo root: {}".format(base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
