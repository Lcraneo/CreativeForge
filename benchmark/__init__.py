"""CreativeForge Benchmark + technical validation system (Phase 9).

Proves, with data, that the self-developed engines (PReCon / FAlign /
GImport) and the autonomous agent outperform naive baselines:

    Dataset -> PReCon / FAlign / GImport / Agent metrics
            -> Evaluation Report -> CF Score

Entry points:

    python -m benchmark.run_benchmark          # write benchmark/results/
    from benchmark.evaluation import EvaluationReport
"""

from benchmark.evaluation import EvaluationReport
from benchmark.score import cf_score

__all__ = ["EvaluationReport", "cf_score"]
