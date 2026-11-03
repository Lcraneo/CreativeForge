class FrameExtractor:
    """Normalizes animation input (sprite sheet / video / gif / AI sequence).

    Output frames carry id + image. Optional upstream hints (anchor, action,
    difference) are preserved so later stages can consume them.
    """

    PRESERVED_HINTS = ("anchor", "action", "difference")

    def process(self, frames):
        normalized_frames = []
        for index, frame in enumerate(frames):
            item = {
                "id": frame.get("id", index),
                "image": frame.get("image")
            }
            for hint in self.PRESERVED_HINTS:
                if hint in frame:
                    item[hint] = frame[hint]
            normalized_frames.append(item)
        return normalized_frames
