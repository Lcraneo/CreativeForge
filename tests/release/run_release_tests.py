"""Phase 10 Release Validation — five layers.

python tests/release/run_release_tests.py [L5 ...]   # 可选：只跑指定层（前缀匹配）

Layer 1  Contract    CreativeAsset / Processor / Adapter still frozen-consistent
Layer 2  Pipeline    Goal -> Agent -> Asset -> Export end to end
Layer 3  Runtime     exported package opens: manifest / anim / prefab parse,
                     animation plays (fps / loop / frames consistent)
Layer 4  Performance planning / agent execution / export timings recorded
Layer 5  Frontend    build artifacts within size budgets, vitest, eslint + tsc
                     （node_modules / dist 缺失时 SKIP，不阻断纯后端发布）
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
                    "anchor": {"root": {"x": 32 + index, "y": 60}, "feet": {"x": 32, "y": 64}},
                }
                for index in range(4)
            ],
        },
    }


# ---------------------------------------------------------------
# Layer 1 — Contract
# ---------------------------------------------------------------


@check("L1 contract", "creative asset schema sections are present")
def _():
    with open(
        os.path.join(ROOT, "schemas", "creative_asset.schema.json"), encoding="utf-8"
    ) as handle:
        schema = json.load(handle)
    required = set(schema["required"])
    assert required == {"identity", "source", "content", "version", "provenance"}
    for section in ("pixel", "animation", "engine", "quality", "style"):
        assert section in schema["properties"]


@check("L1 contract", "processors still speak the AssetProcessor shape")
def _():
    from falign.pipeline.falign_engine import FAlignEngine
    from gimport.pipeline.gimport_engine import GImportEngine
    from precon.pipeline.precon_engine import PReConEngine

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

    result = SupervisorAgent().run("创建一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")

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
        ValueError("boom"),
        executor,
        {"id": "hero001"},
    )
    assert asset is not None
    assert recovery["strategy"] == "fallback"


# ---------------------------------------------------------------
# Layer 3 — Runtime (the exported project opens)
# ---------------------------------------------------------------


def _build_real_package(tmp_dir):
    from agents.supervisor.supervisor import SupervisorAgent
    from studio.backend.export_service.service import ExportService

    asset = SupervisorAgent().run("生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")["asset"]
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
        clip = json.loads(bundle.read("Animation/{}.anim.json".format(asset["id"])).decode())
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
            bundle.read("Character/{}.manifest.json".format(asset["id"])).decode()
        )
        prefab = json.loads(bundle.read("Prefab/{}.prefab.json".format(asset["id"])).decode())
        controller = json.loads(bundle.read("Config/controller.json").decode())

    assert manifest["valid"] is True
    assert prefab["components"] == [
        "SpriteRenderer",
        "Animator",
        "Collider",
        "Script",
        "AnimationController",
    ]
    assert controller["clips"]


# ---------------------------------------------------------------
# Layer 4 — Performance
# ---------------------------------------------------------------


@check("L4 performance", "planning and execution stay fast and bounded")
def _():
    from agent.planner.planner import Planner
    from agents.supervisor.supervisor import SupervisorAgent

    start = time.perf_counter()
    Planner().plan("制作一个像素RPG火焰法师，带攻击动画，导入Unity")
    planning_ms = (time.perf_counter() - start) * 1000
    assert planning_ms < 50, "planning took {:.1f}ms".format(planning_ms)

    tracemalloc.start()
    start = time.perf_counter()
    result = SupervisorAgent().run("制作一个像素RPG火焰法师，带攻击动画，导入Unity")
    execution_ms = (time.perf_counter() - start) * 1000
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result["supervisor"]["status"] == "PASS"
    # Phase 4 起 FAlign 在 Agent 路径真正渲染帧（source-driven，实测约 40s /
    # 33MB），阈值按真实管线校准并保留约 3 倍余量；门限的意义是防失控回退。
    assert execution_ms < 120000, "execution took {:.0f}ms".format(execution_ms)
    assert peak < 128 * 1024 * 1024, "peak memory {:.1f}MB".format(peak / 1048576)
    print(
        "       planning {:.2f}ms | execution {:.1f}ms | peak {:.2f}MB".format(
            planning_ms, execution_ms, peak / 1048576
        )
    )


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


# ---------------------------------------------------------------
# Layer 5 — Frontend（Q4 可持续质量保障）
# ---------------------------------------------------------------

FRONTEND_DIR = os.path.join(ROOT, "studio", "frontend")
DIST_DIR = os.path.join(FRONTEND_DIR, "dist")
ENTRY_GZIP_BUDGET = 130 * 1024  # perf-baseline：入口 gzip 实测 113KB + 余量
CHUNK_RAW_BUDGET = 900 * 1024  # three.js 所在页 chunk 实测 852KB + 余量


class CheckSkipped(Exception):
    """环境不满足（无 node_modules / dist 未构建）时跳过而非失败。"""


def _frontend_ready():
    return os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules"))


def _run_npm(*args):
    import subprocess

    return subprocess.run(
        "npm {}".format(" ".join(args)),
        cwd=FRONTEND_DIR,
        shell=True,  # Windows 需要经 shell 解析 npm.cmd
        capture_output=True,
        text=True,
    )


@check("L5 frontend", "build artifacts exist within size budgets")
def _():
    import glob
    import gzip

    if not os.path.isdir(DIST_DIR):
        raise CheckSkipped("dist 未构建（先 npm run build）")
    assert os.path.isfile(os.path.join(DIST_DIR, "index.html")), "dist/index.html missing"
    js_files = glob.glob(os.path.join(DIST_DIR, "assets", "*.js"))
    assert js_files, "no js bundles in dist/assets"

    oversize = [
        "{} {:.0f}KB".format(os.path.basename(path), os.path.getsize(path) / 1024)
        for path in js_files
        if os.path.getsize(path) > CHUNK_RAW_BUDGET
    ]
    assert not oversize, "chunks over budget: {}".format("; ".join(oversize))

    entries = [p for p in js_files if os.path.basename(p).startswith("index-")]
    assert entries, "entry chunk (index-*.js) missing"
    entry = max(entries, key=os.path.getsize)
    with open(entry, "rb") as handle:
        gzipped = len(gzip.compress(handle.read()))
    assert gzipped <= ENTRY_GZIP_BUDGET, "entry gzip {:.0f}KB > {}KB".format(
        gzipped / 1024, ENTRY_GZIP_BUDGET / 1024
    )
    print("       entry gzip {:.0f}KB | {} js chunks".format(gzipped / 1024, len(js_files)))


@check("L5 frontend", "frontend unit tests (vitest) pass")
def _():
    if not _frontend_ready():
        raise CheckSkipped("node_modules 未安装")
    completed = _run_npm("run", "test")
    assert completed.returncode == 0, "vitest failed:\n{}".format(
        (completed.stdout + completed.stderr)[-800:]
    )


@check("L5 frontend", "frontend lint & types (eslint + tsc) pass")
def _():
    if not _frontend_ready():
        raise CheckSkipped("node_modules 未安装")
    for args, label in ((("run", "lint"), "eslint"), (("run", "typecheck"), "tsc")):
        completed = _run_npm(*args)
        assert completed.returncode == 0, "{} failed:\n{}".format(
            label, (completed.stdout + completed.stderr)[-800:]
        )


def main():
    wanted = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    failures = []
    skipped = 0
    executed = 0
    current = None
    for layer, name, func in CHECKS:
        if wanted and not any(layer.startswith(arg) for arg in wanted):
            continue
        executed += 1
        if layer != current:
            print("== {} ==".format(layer))
            current = layer
        try:
            func()
        except CheckSkipped as reason:
            skipped += 1
            print("  skip  {} ({})".format(name, reason))
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

    print()
    print("{} release checks, {} failed, {} skipped".format(executed, len(failures), skipped))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
