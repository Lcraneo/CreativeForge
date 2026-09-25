"""Benchmark CLI entry point.

    python -m benchmark.run_benchmark

Runs the full Phase 9 benchmark over the dataset with the real engines and
writes benchmark/results/benchmark_report.{json,md}.
"""

import sys

from benchmark.evaluation import EvaluationReport


def main():
    report = EvaluationReport().run()
    json_path, md_path = EvaluationReport().write(report)

    cf = report["cf_score"]
    print("== CreativeForge Benchmark ==")
    print("PReCon  pixel consistency: {:.1%} -> {:.1%} (+{:.1%})".format(
        report["precon"]["baseline_pixel_score"],
        report["precon"]["method_pixel_score"],
        report["precon"]["improvement"]))
    print("FAlign  root drift: {:.2f} -> {:.2f} px/frame (-{:.1%})".format(
        report["falign"]["baseline_root_drift"],
        report["falign"]["method_root_drift"],
        report["falign"]["drift_reduction"]))
    print("GImport success rate: {:.0%}, speedup: {:.0f}x".format(
        report["gimport"]["import_success_rate"],
        report["gimport"]["time_comparison"]["speedup"]))
    print("Agent   completion: {:.0%}, planning: {:.0%}, recovery: {:.0%}".format(
        report["agent"]["task_completion_rate"],
        report["agent"]["planning_accuracy"],
        report["agent"]["recovery_success_rate"]))
    print("CF Score: {:.1%}".format(cf["overall"]))
    print("report: {}".format(json_path))
    print("report: {}".format(md_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
