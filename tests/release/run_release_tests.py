"""Phase 10 Release Validation — four layers.

    python tests/release/run_release_tests.py

    Layer 1  Contract    CreativeAsset / Processor / Adapter still frozen-consistent
    Layer 2  Pipeline    Goal -> Agent -> Asset -> Export end to end
    Layer 3  Runtime     exported package opens: manifest / anim / prefab parse,
                         animation plays (fps / loop / frames consistent)
    Layer 4  Performance planning / agent execution / export timings recorded
"""

import json
import os
import sys
import time
import tracemalloc
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CHECKS = []


def check(layer, name):
    def decorator(func):
        CHECKS.append((layer, name, func))
        return func
    return decorator


def make_asset():
    return {
        "id": "mage001",
        "name": "FireMage",
        "type": "character",
        "source": {"width": 64, "height": 64, "prompt": "fire mage"},
        "animation": {
            "action": "attack",
            "fps": 12,
            "loop": True,
            "frames": [
                {
                    "id": index,
                    "image": "frame{}.png".format(index),
                    "action": "attack",
                    "anchor": {
                        "root": {"x": 32 + index, "y": 60},
                        "feet": {"x": 32, "y": 64}
                    }
                }
                for index in range(4)
            ]
        }
    }


# ---------------------------------------------------------------
# Layer 1 — Contract
# ---------------------------------------------------------------

@check("L1 contract", "creative asset schema sections are present")
def _():
    with open(os.path.join(ROOT, "schemas", "creative_asset.schema.json"),
              encoding="utf-8") as handle:
        schema = json.load(handle)
    required = set(schema["required"])
    assert required == {"identity", "source", "content", "version", "provenance"}
    for section in ("pixel", "animation", "engine", "quality", "style"):
        assert section in schema["properties"]


@check("L1 contract", "processors still speak the AssetProcessor shape")
def _():
    from precon.pipeline.precon_engine import PReConEngine
    from falign.pipeline.falign_engine import FAlignEngine
    from gimport.pipeline.gimport_engine import GImportEngine

    for engine in (PReConEngine(), FAlignEngine(), GImportEngine()):
        assert hasattr(engine, "process")


@check("L1 contract", "adapters import and export CreativeAsset")
def _():
    from adapters.creative_asset_adapter import CreativeAssetAdapter
    from gimport.adapters.unity_adapter import UnityAdapter

    result = CreativeAssetAdapter().export_asset(make_asset())
    assert result["animation"]["anchor"]

    unity = UnityAdapter().import_asset({"id": "hero001"})
    assert unity["resources"]["Prefab"] == "Assets/Prefab/hero001.prefab"


# ---------------------------------------------------------------
# Layer 2 — Pipeline
# ---------------------------------------------------------------

@check("L2 pipeline", "goal to engine package in one supervisor run")
def _():
    from agents.supervisor.supervisor import SupervisorAgent

    result = SupervisorAgent().run(
        "创建一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")

    assert result["supervisor"]["status"] == "PASS"
    asset = result["asset"]
    assert asset["engine"]["target"] == "unity"
    assert asset["engine"]["validation"]["status"] == "success"
    assert asset["quality"]["report"]["status"] == "PASS"


@check("L2 pipeline", "one-click export produces the full package")
def _():
    from gimport.exporter.one_click_export import OneClickExporter

    export = OneClickExporter().export(make_asset(), "unity")
    assert export["package"] == "FireMageGameAsset.zip"
    assert export["contents"] == ["Character", "Animation", "Prefab", "Config"]
    assert export["result"]["validation"]["status"] == "success"


@check("L2 pipeline", "fallback recovery keeps the pipeline alive")
def _():
    from agent.recovery.recovery_manager import RecoveryManager

    class FailingUnity:
        def __init__(self):
            self.calls = []

        def execute(self, task, asset):
            self.calls.append(task.get("engine"))
            if task.get("engine") == "unity":
                raise ValueError("engine failure")
            return asset

    executor = FailingUnity()
    asset, recovery = RecoveryManager(max_retries=1).recover(
        {"id": "T1", "capability": "GImport", "engine": "unity"},
        ValueError("boom"), executor, {"id": "hero001"})
    assert asset is not None
    assert recovery["strategy"] == "fallback"


# ---------------------------------------------------------------
# Layer 3 — Runtime (the exported project opens)
# ---------------------------------------------------------------

def _build_real_package(tmp_dir):
    from studio.backend.export_service.service import ExportService
    from agents.supervisor.supervisor import SupervisorAgent

    asset = SupervisorAgent().run(
        "生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")["asset"]
    return ExportService(tmp_dir).export(asset, "unity"), asset


@check("L3 runtime", "exported zip opens and every file parses")
def _():
    out = os.path.join(ROOT, "tests", "release", "_tmp_runtime")
    os.makedirs(out, exist_ok=True)
    export, _ = _build_real_package(out)

    package_path = os.path.join(out, export["package"])
    assert zipfile.is_zipfile(package_path)
    with zipfile.ZipFile(package_path) as bundle:
        names = bundle.namelist()
        assert len(names) == len(export["files"])
        for name in names:
            if name.endswith(".json"):
                json.loads(bundle.read(name).decode("utf-8"))


@check("L3 runtime", "animation clip plays: fps / loop / frames consistent")
def _():
    out = os.path.join(ROOT, "tests", "release", "_tmp_runtime")
    export, asset = _build_real_package(out)

    with zipfile.ZipFile(os.path.join(out, export["package"])) as bundle:
        clip = json.loads(
            bundle.read("Animation/{}.anim.json".format(asset["id"])).decode())
        atlas = json.loads(bundle.read("Config/atlas.json").decode())

    assert clip["loop"] is True
    assert clip["fps"] == asset["animation"]["fps"]
    assert clip["frame_count"] == len(atlas["frames"])
    assert clip["frame_count"] == len(asset["animation"]["frames"])


@check("L3 runtime", "prefab manifest and controller wire the entity")
def _():
    out = os.path.join(ROOT, "tests", "release", "_tmp_runtime")
    export, asset = _build_real_package(out)

    with zipfile.ZipFile(os.path.join(out, export["package"])) as bundle:
        manifest = json.loads(
            bundle.read("Character/{}.manifest.json".format(asset["id"])).decode())
        prefab = json.loads(
            bundle.read("Prefab/{}.prefab.json".format(asset["id"])).decode())
        controller = json.loads(bundle.read("Config/controller.json").decode())

    assert manifest["valid"] is True
    assert prefab["components"] == [
        "SpriteRenderer", "Animator", "Collider", "Script", "AnimationController"]
    assert controller["clips"]


# ---------------------------------------------------------------
# Layer 4 — Performance
# ---------------------------------------------------------------

@check("L4 performance", "planning and execution stay fast and bounded")
def _():
    from agent.planner.planner import Planner
    from agents.supervisor.supervisor import SupervisorAgent

    start = time.perf_counter()
    plan = Planner().plan("制作一个像素RPG火焰法师，带攻击动画，导入Unity")
    planning_ms = (time.perf_counter() - start) * 1000
    assert planning_ms < 50, "planning took {:.1f}ms".format(planning_ms)

    tracemalloc.start()
    start = time.perf_counter()
    result = SupervisorAgent().run(
        "制作一个像素RPG火焰法师，带攻击动画，导入Unity")
    execution_ms = (time.perf_counter() - start) * 1000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result["supervisor"]["status"] == "PASS"
    assert execution_ms < 2000, "execution took {:.0f}ms".format(execution_ms)
    assert peak < 32 * 1024 * 1024, "peak memory {:.1f}MB".format(peak / 1048576)
    print("       planning {:.2f}ms | execution {:.1f}ms | peak {:.2f}MB".format(
        planning_ms, execution_ms, peak / 1048576))


@check("L4 performance", "export completes in seconds")
def _():
    from gimport.exporter.one_click_export import OneClickExporter

    start = time.perf_counter()
    export = OneClickExporter().export(make_asset(), "unity")
    elapsed = time.perf_counter() - start
    assert export["result"]["validation"]["status"] == "success"
    assert elapsed < 1.0, "export took {:.2f}s".format(elapsed)


@check("L4 performance", "benchmark reaches release thresholds")
def _():
    from benchmark.evaluation import EvaluationReport

    report = EvaluationReport().run()
    cf = report["cf_score"]
    assert report["precon"]["method_pixel_score"] >= 0.85
    assert report["falign"]["method_root_drift"] <= 0.1
    assert report["gimport"]["import_success_rate"] >= 0.99
    assert report["agent"]["task_completion_rate"] >= 0.9
    assert cf["overall"] >= 0.9


def main():
    failures = []
    current = None
    for layer, name, func in CHECKS:
        if layer != current:
            print("== {} ==".format(layer))
            current = layer
        try:
            func()
        except AssertionError as error:
            failures.append((layer, name, str(error)))
            print("  FAIL {}".format(name))
            if str(error):
                print("       {}".format(error))
        except Exception as error:
            failures.append((layer, name, "{}: {}".format(type(error).__name__, error)))
            print("  ERROR {} ({}: {})".format(name, type(error).__name__, error))
        else:
            print("  ok   {}".format(name))

    total = len(CHECKS)
    print()
    print("{} release checks, {} failed".format(total, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
