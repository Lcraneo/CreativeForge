DEFAULT_FPS = 12


class AnimationClipGenerator:
    """Reads the FAlign-aligned animation state and emits engine clip config.

    Unity clips carry fps + loop; Cocos clips carry duration + loop.
    """

    def generate(self, asset, engine="cocos"):
        animation = asset.get("animation", {})
        frames = animation.get("frames", [])
        action = (
            animation.get("phase", {}).get("action")
            or animation.get("action", "idle")
        )
        fps = animation.get("fps", DEFAULT_FPS)
        loop = animation.get("loop", True)
        frame_count = len(frames)

        if engine == "unity":
            return {
                "clip": {
                    "name": action,
                    "fps": fps,
                    "loop": loop,
                    "frame_count": frame_count
                }
            }

        duration = round(frame_count / fps, 2) if fps else 0.0
        return {
            "animation": {
                "name": action,
                "duration": duration,
                "loop": loop,
                "frame_count": frame_count,
                "sample": fps
            }
        }
