from agent.generation.builder import build_asset, edit_asset
from gimport.pipeline.gimport_engine import GImportEngine
from precon.pipeline.precon_engine import PReConEngine
from precon.quality import evaluate_pixel


class Capability:
    """One registered capability: the Planner selects these, never code."""

    def __init__(
        self,
        name,
        type,
        handler=None,
        agent=None,
        input="CreativeAsset",
        output="CreativeAsset",
        cost=0.0,
        quality=1.0,
    ):
        self.name = name
        self.type = type
        self.handler = handler
        self.agent = agent
        self.input = input
        self.output = output
        self.cost = cost
        self.quality = quality

    def to_dict(self):
        return {
            "name": self.name,
            "type": self.type,
            "input": self.input,
            "output": self.output,
            "cost": self.cost,
            "quality": self.quality,
        }


class CapabilityRegistry:

    def __init__(self):
        self._capabilities = {}

    def register(self, capability):
        self._capabilities[capability.name] = capability

    def find(self, name):
        return self._capabilities.get(name)

    def capabilities(self):
        return list(self._capabilities.values())


def generate_asset(asset, task):
    """Prompt-driven generation.

    Different goals produce different characters (id / name / palette /
    animation / seed); the canonical fire-mage prompt keeps its historical
    ``mage001`` / ``FireMage`` identity so the demo and benchmarks stay stable.
    """
    if asset:
        return asset
    goal = (task or {}).get("goal", "")
    return build_asset(goal, task)


def _reconstruct_from_ai_image(source, style):
    """Real PReCon source: decode the AI artwork, downsample it onto the
    style lattice and quantize to the style palette. Returns the pixel
    payload (with a ``pixels`` colour matrix) or None when unavailable."""

    image_ref = source.get("ai_image") or {}
    path = image_ref.get("path")
    if not path:
        return None

    try:
        from PIL import Image

        with Image.open(path) as handle:
            handle.load()
            rgba = handle.convert("RGBA")
    except Exception:
        return None

    grid_size = int(source.get("grid_size", 16 if style == "2d" else 8) or 16)
    max_colors = 32 if style == "2d" else 16

    try:
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        composited = Image.alpha_composite(background, rgba).convert("RGB")
        small = composited.resize((grid_size, grid_size), Image.BOX)
        alpha_small = rgba.split()[3].resize((grid_size, grid_size), Image.BOX)

        quantized = small.quantize(colors=max_colors, method=Image.MEDIANCUT)
        raw_palette = quantized.getpalette() or []

        def _hexat(index):
            r, g, b = raw_palette[index * 3 : index * 3 + 3]
            return "#{:02x}{:02x}{:02x}".format(r, g, b)

        colors = []
        seen = set()
        matrix = []
        alpha_pixels = alpha_small.load()
        quant_pixels = quantized.load()
        for y in range(grid_size):
            row = []
            for x in range(grid_size):
                if alpha_pixels[x, y] < 40:
                    row.append(None)
                    continue
                index = quant_pixels[x, y]
                color = _hexat(index)
                if color not in seen:
                    seen.add(color)
                    colors.append(color)
                row.append(color)
            matrix.append(row)

        if not colors:
            return None

        roles = source.get("palette") or {}
        contour_style = "soft" if style == "2d" else "hard"
        grid = {"size": grid_size, "phase_x": 0, "phase_y": 0, "confidence": 0.97}
        palette = {
            "max_colors": max(max_colors, len(colors)),
            "colors": colors,
            "semantic_roles": {
                "outline": roles.get("outline"),
                "shadow": roles.get("shadow"),
                "base": roles.get("base"),
                "highlight": roles.get("highlight"),
                "accent": roles.get("accent"),
                "hair": roles.get("hair"),
                "skin": roles.get("skin"),
                "eyes": roles.get("eyes"),
                "metal": roles.get("metal"),
            },
            "source": "ai-image",
        }
        contour = {
            "thickness": 1,
            "connectivity": 8,
            "style": contour_style,
            "repaired": True,
            "repaired_pixels": 0,
        }
        return {
            "pixel": {
                "grid": grid,
                "palette": palette,
                "contour": contour,
                "pixels": matrix,
                "style": style or "pixel",
            },
            "quality": evaluate_pixel(grid, palette, contour),
        }
    except Exception:
        return None


def edit_existing_asset(asset, task):
    return edit_asset(asset, (task or {}).get("goal", ""), task)


def inspect_asset(asset, task):
    if asset is None:
        raise ValueError("inspect_asset requires an existing CreativeAsset")
    asset.setdefault("agent", {})["last_intent"] = (task or {}).get("goal", "")
    return asset


def run_precon(asset, task):
    source = dict(asset.get("source") or {"width": 64, "height": 64})
    character = asset.get("character") or {}

    if source.get("seed") is None and character.get("seed") is not None:
        source["seed"] = character["seed"]
    if not source.get("palette") and character.get("palette"):
        source["palette"] = character["palette"]

    style = (
        source.get("style")
        or character.get("style")
        or ((task or {}).get("overrides") or {}).get("style")
    )

    # A real AI artwork (when configured and produced) is the primary source;
    # the deterministic synthetic sprite is the fallback.
    result = _reconstruct_from_ai_image(source, style)
    if result is None:
        result = PReConEngine().process(source, style=style)

    asset["pixel"] = result["pixel"]
    asset.setdefault("quality", {})["pixel"] = result["quality"]
    return asset


def run_falign(asset, task):
    if asset is None:
        raise ValueError("FAlign requires a CreativeAsset")

    animation = asset.setdefault("animation", {})
    action = (task or {}).get("action_name") or animation.get("action") or "walk"
    if action not in {"idle", "walk", "run", "attack", "jump", "cast", "hit"}:
        action = "walk"

    # The Agent path must produce real frames before FAlign. Prefer the actual
    # AI artwork; when no external artwork exists, render the current asset
    # itself. This keeps the dynamic Studio workflow useful without inventing
    # a separate fixed demo character.
    source_bytes = None
    source = asset.get("source") or {}
    image = asset.get("image") or {}
    candidates = [image, source.get("ai_image") if isinstance(source, dict) else None]
    for meta in candidates:
        if not isinstance(meta, dict):
            continue
        path = meta.get("path")
        if path:
            try:
                with open(path, "rb") as handle:
                    source_bytes = handle.read()
                break
            except OSError:
                pass

    if source_bytes is None:
        try:
            from artgen import render_asset_view

            source_bytes = render_asset_view(asset, "front", 384)
        except Exception as error:
            raise RuntimeError("无法为 FAlign 获取当前角色源图: {}".format(error))

    from artgen.pipeline import create_animation
    from falign.pipeline.falign_engine import FAlignEngine

    fps = int(animation.get("fps", 12) or 12)
    result = create_animation(
        source_bytes=source_bytes,
        action=action,
        fps=fps,
        duration=max(0.5, min(4.0, float(animation.get("duration", 1.0) or 1.0))),
        size=384,
        view="front",
    )

    prepared = [
        {"id": index, "image": frame, "action": action}
        for index, frame in enumerate(result["frames"])
    ]
    aligned = FAlignEngine().process(prepared)

    # Keep CreativeAsset JSON-safe: raw PNG bytes stay in the animation result
    # only through derived render metadata, while FAlign keeps its structural
    # frame/anchor/phase information on the asset contract.
    animation.update(aligned["animation"])
    animation["frames"] = [
        {"id": index, "action": action, "image": None} for index in range(len(result["frames"]))
    ]
    animation["fps"] = result["fps"]
    animation["loop"] = result["loop"]
    animation["render"] = {
        "action": result["action"],
        "frame_count": result["frame_count"],
        "duration": result["duration"],
        "size": result["size"],
        "consistency": result["consistency"],
        "source": "current-character-source",
    }
    asset.setdefault("quality", {})["animation"] = aligned["quality"]["animation"]
    return asset


def run_gimport(asset, task):
    engine = (task or {}).get("engine", "cocos")
    result = GImportEngine().process(asset, engine)
    asset["engine"] = {
        "target": engine,
        "manifest": result["manifest"],
        "validation": result["validation"],
        "resources": result["engine"]["resources"],
    }
    asset.setdefault("quality", {})["engine"] = {
        "overall": result["validation"]["score"],
        "status": result["validation"]["status"],
    }
    return asset


def run_onetake_showcase(asset, task):
    """motion_video_generation（OneTake External Capability）：CreativeAsset →
    发布展示计划。纯映射（scene/timeline mapper），真实渲染走 studio 的
    ShowcaseService 任务队列（懒加载 adapters，legacy 管线零依赖）。"""

    asset = asset or {}
    if asset.get("id") is None and not asset.get("name"):
        raise ValueError("motion_video_generation requires an existing CreativeAsset")
    from adapters.onetake.asset_mapper import slugify
    from adapters.onetake.scene_mapper import build_scene
    from adapters.onetake.timeline_mapper import build_timeline

    material = {
        "name": asset.get("name"),
        "prompt": ((asset.get("identity") or {}).get("prompt") or asset.get("name") or ""),
        "slug": slugify(asset.get("name") or asset.get("id")),
    }
    presentation = asset.get("presentation") or {}
    scene = build_scene(material, presentation)
    cf = build_timeline(scene, {}, presentation)
    asset.setdefault("presentation", {}).update(
        {
            "type": "launch_video",
            "style": "one_take",
            "duration": cf["meta"]["dur"],
            "camera": "continuous",
            "look": "cf-paper",
            "storyboard": {
                "beats": list(cf["beats"].keys()),
                "copy": cf["copy"],
                "shots": cf["cuts"],
            },
        }
    )
    return asset


def build_default_registry():
    """Default capability registry binding the Phase 1-5 engines."""
    registry = CapabilityRegistry()
    registry.register(
        Capability(
            "generation",
            "generator",
            handler=generate_asset,
            input="Prompt|CreativeAsset",
            output="CreativeAsset",
            cost=1.0,
            quality=0.9,
        )
    )
    registry.register(Capability("PReCon", "processor", handler=run_precon, cost=0.2, quality=0.95))
    registry.register(
        Capability("asset_edit", "transformer", handler=edit_existing_asset, cost=0.1, quality=0.9)
    )
    registry.register(Capability("FAlign", "processor", handler=run_falign, cost=0.2, quality=0.95))
    registry.register(
        Capability("GImport", "exporter", handler=run_gimport, cost=0.1, quality=0.96)
    )
    registry.register(
        Capability(
            "motion_video_generation",
            "publisher",
            handler=run_onetake_showcase,
            input="CreativeAsset",
            output="CreativeAsset",
            cost=0.3,
            quality=0.9,
        )
    )
    return registry
