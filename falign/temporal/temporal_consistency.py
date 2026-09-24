DEFAULT_DIFFERENCE = 0.04
JITTER_THRESHOLD = 0.1


class TemporalAnalyzer:
    """Measures adjacent-frame difference (pixel + feature in production).

    Frames may carry an explicit ``difference`` hint; otherwise the default
    inter-frame difference is assumed.
    """

    def analyze(self, frames):
        pairs = max(len(frames) - 1, 0)
        if pairs == 0:
            return {
                "jitter_score": 0.0,
                "smooth": True,
                "differences": []
            }

        differences = [
            abs(float(frame.get("difference", DEFAULT_DIFFERENCE)))
            for frame in frames[1:]
        ]
        jitter_score = sum(differences) / len(differences)
        return {
            "jitter_score": round(jitter_score, 4),
            "smooth": jitter_score < JITTER_THRESHOLD,
            "differences": [round(difference, 4) for difference in differences]
        }
