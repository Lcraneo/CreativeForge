DEFAULT_FRAME_SIZE = 64
MAX_COLUMNS = 8


class SpriteAtlasBuilder:
    """Packs frame images into one sprite atlas (fewer draw calls, simpler
    resource management)."""

    def build(self, asset):
        animation = asset.get("animation", {})
        frames = animation.get("frames", [])
        action = (
            animation.get("phase", {}).get("action")
            or animation.get("action", "idle")
        )
        asset_id = asset.get("id", "asset000")

        frame_width, frame_height = self._frame_size(asset)
        columns = min(len(frames), MAX_COLUMNS) or 1
        rows = (len(frames) + columns - 1) // columns

        names = []
        layout = []
        for index, frame in enumerate(frames):
            name = "{}_{}".format(frame.get("action", action), frame.get("id", index))
            column = index % columns
            row = index // columns
            names.append(name)
            layout.append({
                "name": name,
                "rect": {
                    "x": column * frame_width,
                    "y": row * frame_height,
                    "w": frame_width,
                    "h": frame_height
                }
            })

        return {
            "atlas": {
                "name": asset_id,
                "image": "{}_sprite_atlas.png".format(asset_id),
                "size": {
                    "width": columns * frame_width,
                    "height": rows * frame_height
                },
                "frames": names,
                "layout": layout
            }
        }

    def _frame_size(self, asset):
        source = asset.get("source", {})
        frame_size = source.get("frame_size") or {}
        return (
            frame_size.get("width", DEFAULT_FRAME_SIZE),
            frame_size.get("height", DEFAULT_FRAME_SIZE)
        )
