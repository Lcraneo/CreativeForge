from precon.pipeline.precon_engine import PReConEngine
from adapters.creative_asset_adapter import CreativeAssetAdapter
from gimport.pipeline.gimport_engine import GImportEngine
from agent.generation.builder import build_asset


class Capability:
    """One registered capability: the Planner selects these, never code."""

    def __init__(self, name, type, handler=None, agent=None,
                 input="CreativeAsset", output="CreativeAsset",
                 cost=0.0, quality=1.0):
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
            "quality": self.quality
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


def run_precon(asset, task):
    source = dict(asset.get("source") or {"width": 64, "height": 64})
    character = asset.get("character") or {}

    if source.get("seed") is None and character.get("seed") is not None:
        source["seed"] = character["seed"]
    if not source.get("palette") and character.get("palette"):
        source["palette"] = character["palette"]

    result = PReConEngine().process(source)
    asset["pixel"] = result["pixel"]
    asset.setdefault("quality", {})["pixel"] = result["quality"]
    return asset


def run_falign(asset, task):
    return CreativeAssetAdapter().export_asset(asset)


def run_gimport(asset, task):
    engine = (task or {}).get("engine", "cocos")
    result = GImportEngine().process(asset, engine)
    asset["engine"] = {
        "target": engine,
        "manifest": result["manifest"],
        "validation": result["validation"],
        "resources": result["engine"]["resources"]
    }
    asset.setdefault("quality", {})["engine"] = {
        "overall": result["validation"]["score"],
        "status": result["validation"]["status"]
    }
    return asset


def build_default_registry():
    """Default capability registry binding the Phase 1-5 engines."""
    registry = CapabilityRegistry()
    registry.register(Capability(
        "generation", "generator", handler=generate_asset,
        input="Prompt", output="CreativeAsset", cost=1.0, quality=0.9
    ))
    registry.register(Capability(
        "PReCon", "processor", handler=run_precon, cost=0.2, quality=0.95
    ))
    registry.register(Capability(
        "FAlign", "processor", handler=run_falign, cost=0.2, quality=0.95
    ))
    registry.register(Capability(
        "GImport", "exporter", handler=run_gimport, cost=0.1, quality=0.96
    ))
    return registry
