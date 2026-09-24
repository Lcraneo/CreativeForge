QUALITY_THRESHOLDS = {
    "pixel": 0.8,
    "animation": 0.85,
    "engine": 0.9
}


class QualityGate:
    """Unified check over the quality sections written by PReCon / FAlign /
    GImport; sections below threshold request a re-run."""

    def check(self, asset):
        quality = asset.get("quality", {})

        scores = {}
        for section in QUALITY_THRESHOLDS:
            value = quality.get(section, {}).get("overall")
            if value is not None:
                scores[section] = value

        retry = [
            section
            for section, value in scores.items()
            if value < QUALITY_THRESHOLDS[section]
        ]

        if not scores:
            status = "PENDING"
        elif retry:
            status = "RETRY"
        else:
            status = "PASS"

        return {
            "scores": scores,
            "thresholds": dict(QUALITY_THRESHOLDS),
            "retry": retry,
            "status": status
        }
