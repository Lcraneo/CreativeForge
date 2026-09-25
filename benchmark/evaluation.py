"""Evaluation Report: runs the full benchmark and assembles the result.

    Dataset -> PReCon / FAlign / GImport / Agent sections
            -> CF Score -> JSON + Markdown report

The markdown mirrors the competition PPT technical-metrics page: pixel
consistency gain, drift reduction, import speedup, agent autonomy.
"""

import os
from datetime import datetime, timezone

from benchmark import dataset as dataset_module
from benchmark import score as score_module
from benchmark.metrics import agent_metrics, animation_metrics, engine_metrics, pixel_metrics

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def _mean(values):
    values = [value for value in values if value is not None]
    return round(sum(values) / float(len(values)), 4) if values else 0.0


class EvaluationReport:

    def __init__(self, entries=None):
        self.entries = entries if entries is not None else dataset_module.ENTRIES

    def run(self):
        precon = self._run_precon()
        falign = self._run_falign()
        gimport = engine_metrics.evaluate(self.entries)
        agent = agent_metrics.evaluate(self.entries)

        cf = score_module.cf_score(
            pixel=precon["method_pixel_score"],
            animation=falign["method_overall"],
            engine=gimport["import_success_rate"],
            agent=(agent["task_completion_rate"]
                   + agent["planning_accuracy"]
                   + agent["recovery_success_rate"]) / 3.0
        )

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": {
                "size": len(self.entries),
                "categories": list(dataset_module.CATEGORIES),
                "animated": len(dataset_module.animated_entries())
            },
            "precon": precon,
            "falign": falign,
            "gimport": gimport,
            "agent": agent,
            "cf_score": cf
        }

    # -------------------------------------------------------------
    # sections
    # -------------------------------------------------------------

    def _run_precon(self):
        comparisons = [pixel_metrics.compare(entry) for entry in self.entries]
        return {
            "baseline_pixel_score": _mean(
                item["baseline"]["pixel_score"] for item in comparisons),
            "method_pixel_score": _mean(
                item["method"]["pixel_score"] for item in comparisons),
            "improvement": _mean(item["delta"]["pixel_score"] for item in comparisons),
            "baseline_colors": _mean(item["baseline"]["colors"] for item in comparisons),
            "method_colors": _mean(item["method"]["colors"] for item in comparisons),
            "baseline_contour": _mean(item["baseline"]["contour"] for item in comparisons),
            "method_contour": _mean(item["method"]["contour"] for item in comparisons),
            "comparisons": comparisons
        }

    def _run_falign(self):
        comparisons = [
            animation_metrics.compare(entry)
            for entry in dataset_module.animated_entries()
        ]
        method_overall = _mean(item["method"]["overall"] for item in comparisons)
        return {
            "baseline_root_drift": _mean(
                item["baseline"]["root_drift"] for item in comparisons),
            "method_root_drift": _mean(
                item["method"]["root_drift"] for item in comparisons),
            "drift_reduction": _mean(
                item["method"]["drift_reduction"] for item in comparisons),
            "baseline_foot_sliding": _mean(
                item["baseline"]["foot_sliding"] for item in comparisons),
            "method_foot_sliding": _mean(
                item["method"]["foot_sliding"] for item in comparisons),
            "baseline_smoothness": _mean(
                item["baseline"]["smoothness"] for item in comparisons),
            "method_smoothness": _mean(
                item["method"]["smoothness"] for item in comparisons),
            "method_overall": method_overall,
            "comparisons": comparisons
        }

    # -------------------------------------------------------------
    # rendering
    # -------------------------------------------------------------

    def to_markdown(self, report):
        precon, falign = report["precon"], report["falign"]
        gimport, agent = report["gimport"], report["agent"]
        cf = report["cf_score"]

        lines = [
            "# CreativeForge Benchmark Report",
            "",
            "Generated: {}".format(report["generated_at"]),
            "Dataset: {} assets across {} categories ({} animated)".format(
                report["dataset"]["size"], len(report["dataset"]["categories"]),
                report["dataset"]["animated"]),
            "",
            "## PReCon — pixel reconstruction vs naive pixelate",
            "",
            "| Method | Colors | Contour | Pixel Consistency |",
            "| ------ | ------ | ------- | ----------------- |",
            "| NaivePixelate | {:.0f} | {:.0%} | {:.0%} |".format(
                precon["baseline_colors"], precon["baseline_contour"],
                precon["baseline_pixel_score"]),
            "| PReCon | {:.0f} | {:.0%} | {:.0%} |".format(
                precon["method_colors"], precon["method_contour"],
                precon["method_pixel_score"]),
            "",
            "Pixel consistency improvement: **+{:.1%}**".format(precon["improvement"]),
            "",
            "## FAlign — frame alignment vs raw AI animation",
            "",
            "| Method | Root Drift (px/frame) | Foot Sliding | Smoothness |",
            "| ------ | --------------------- | ------------ | ---------- |",
            "| RawAIFrames | {:.2f} | {:.0%} | {:.0%} |".format(
                falign["baseline_root_drift"], falign["baseline_foot_sliding"],
                falign["baseline_smoothness"]),
            "| FAlign | {:.2f} | {:.0%} | {:.0%} |".format(
                falign["method_root_drift"], falign["method_foot_sliding"],
                falign["method_smoothness"]),
            "",
            "Drift reduction: **-{:.1%}**".format(falign["drift_reduction"]),
            "",
            "## GImport — one-click import vs traditional manual flow",
            "",
            "| Flow | Steps | Time |",
            "| ---- | ----- | ---- |",
            "| Traditional | {} | {} min |".format(
                gimport["manual_reduction"]["traditional_steps"],
                gimport["time_comparison"]["traditional_minutes"]),
            "| GImport | {} | {:.2f} s |".format(
                gimport["manual_reduction"]["gimport_steps"],
                gimport["average_pipeline_seconds"]),
            "",
            "Import success rate: **{:.0%}**, speedup: **{:.0f}x**".format(
                gimport["import_success_rate"],
                gimport["time_comparison"]["speedup"]),
            "",
            "## Agent — autonomous planning",
            "",
            "- Task completion rate: **{:.0%}** ({}/{})".format(
                agent["task_completion_rate"], agent["completed"], agent["total"]),
            "- Planning accuracy: **{:.0%}**".format(agent["planning_accuracy"]),
            "- Recovery success rate: **{:.0%}**".format(agent["recovery_success_rate"]),
            "- Average task time: **{:.2f}s**".format(agent["average_task_seconds"]),
            "",
            "## CF Score",
            "",
            "| Component | Weight | Score |",
            "| --------- | ------ | ----- |",
        ]
        for name in ("pixel", "animation", "engine", "agent"):
            lines.append("| {} | {:.0%} | {:.0%} |".format(
                name, cf["weights"][name], cf["components"][name]))
        lines += [
            "| **overall** | 1.00 | **{:.1%}** |".format(cf["overall"]),
            "",
        ]
        return "\n".join(lines)

    def write(self, report, results_dir=RESULTS_DIR):
        os.makedirs(results_dir, exist_ok=True)
        json_path = os.path.join(results_dir, "benchmark_report.json")
        md_path = os.path.join(results_dir, "benchmark_report.md")
        import json
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(self.to_markdown(report))
        return json_path, md_path
