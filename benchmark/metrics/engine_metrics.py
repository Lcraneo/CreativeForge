"""GImport benchmark metrics (Phase 9, section 七/八).

Validates: "从 AI 资产到游戏工程的自动化能力。"

Comparison:
    Traditional  AI Asset -> manual cut -> animation config -> Prefab -> import
                 12 manual steps, 30-60 minutes
    GImport      CreativeAsset -> Manifest -> Atlas -> Animation -> Prefab -> Export
                 1 step, seconds

Metrics:
    Import Success Rate (ISR)  successfully imported ratio
    Pipeline Time              generation time in seconds (measured)
    Manual Operation Reduction 12 manual steps -> 1
"""

import time

TRADITIONAL_STEPS = 12
TRADITIONAL_MINUTES = 45
# Phase 9 production reference: a full engine export with real asset IO
# budgeted at 60 s; the microbenchmark below measures the in-process part.
REFERENCE_EXPORT_SECONDS = 60


def import_success_rate(results):
    """ISR over GImport result rows: either flat evaluate() rows with a
    top-level "status", or raw engine results with validation.status."""
    if not results:
        return 0.0
    passed = 0
    for result in results:
        status = result.get("status")
        if status is None:
            status = result.get("validation", {}).get("status")
        if status == "success":
            passed += 1
    return round(passed / float(len(results)), 4)


def measure_pipeline_time(func, *args, **kwargs):
    """Run one export and measure wall-clock seconds."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, round(elapsed, 4)


def manual_operation_reduction():
    """Manual steps: traditional 12 vs GImport 1."""
    return {
        "traditional_steps": TRADITIONAL_STEPS,
        "gimport_steps": 1,
        "reduction": TRADITIONAL_STEPS - 1
    }


def time_comparison(measured_seconds):
    """Traditional 45 min vs the 60 s production reference export."""
    return {
        "traditional_minutes": TRADITIONAL_MINUTES,
        "reference_seconds": REFERENCE_EXPORT_SECONDS,
        "speedup": round(TRADITIONAL_MINUTES * 60.0 / REFERENCE_EXPORT_SECONDS, 1),
        "measured_seconds": round(measured_seconds, 4)
    }


def build_asset(entry):
    """Dataset entry -> importable CreativeAsset. Static assets (weapons /
    tilesets) import as a single-frame animation, the engine convention."""
    frames = max(1, entry["frames"])
    action = entry["action"] or "idle"
    return {
        "id": entry["id"],
        "name": entry["id"].title().replace("_", ""),
        "type": entry["type"],
        "source": {"width": 64, "height": 64, "prompt": entry["goal"]},
        "animation": {
            "action": action,
            "fps": 12,
            "loop": True,
            "frames": [
                {
                    "id": index,
                    "image": "frame{}.png".format(index),
                    "action": action,
                    "anchor": {
                        "root": {"x": 32, "y": 60},
                        "feet": {"x": 32, "y": 64}
                    }
                }
                for index in range(frames)
            ]
        }
    }


def evaluate(entries):
    """Run GImport over every dataset entry on its target engine."""
    from gimport.exporter.one_click_export import OneClickExporter

    exporter = OneClickExporter()
    results = []
    total_time = 0.0
    for entry in entries:
        export, elapsed = measure_pipeline_time(
            exporter.export, build_asset(entry), entry["engine"])
        total_time += elapsed
        results.append({
            "id": entry["id"],
            "engine": entry["engine"],
            "status": export["result"]["validation"]["status"],
            "score": export["result"]["validation"]["score"],
            "package": export["package"],
            "seconds": elapsed
        })

    average_time = total_time / len(results) if results else 0.0
    return {
        "import_success_rate": import_success_rate(results),
        "results": results,
        "average_pipeline_seconds": round(average_time, 4),
        "manual_reduction": manual_operation_reduction(),
        "time_comparison": time_comparison(average_time)
    }
