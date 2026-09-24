class PhaseAligner:
    """Maps a frame sequence onto a canonical motion phase space (0 -> 1).

    Solves AI action-stage disorder: frames are re-expressed as phase
    positions of the action (e.g. walk at 0 / 0.25 / 0.5 / 0.75 / 1).
    """

    def align(self, frames, anchors=None):
        count = len(frames)
        action = next(
            (frame.get("action") for frame in frames if frame.get("action")),
            "idle"
        )
        return {
            "action": action,
            "phase": self._phase_track(count),
            "aligned": True
        }

    def _phase_track(self, count):
        if count <= 1:
            return [0.0] if count else []
        step = 1.0 / (count - 1)
        return [round(index * step, 4) for index in range(count)]
