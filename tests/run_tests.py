"""Runnable contract tests for CreativeForge (Phases 3-7).

Run from the repository root:

    python tests/run_tests.py

Each check mirrors the markdown contract docs in tests/.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CHECKS = []


def check(group, name):
    def decorator(func):
        CHECKS.append((group, name, func))
        return func

    return decorator


def make_asset(action="walk", count=4):
    return {
        "id": "mage001",
        "name": "FireMage",
        "type": "character",
        "source": {"width": 64, "height": 64, "prompt": "fire mage"},
        "animation": {
            "action": action,
            "fps": 12,
            "loop": True,
            "frames": [
                {
                    "id": index,
                    "image": "frame{}.png".format(index),
                    "action": action,
                    "anchor": {"root": {"x": 32 + index, "y": 60}, "feet": {"x": 32, "y": 64}},
                }
                for index in range(count)
            ],
        },
    }


# ---------------------------------------------------------------
# FAlign (Phase 4)
# ---------------------------------------------------------------


@check("falign", "frame extraction normalizes frames and preserves hints")
def _():
    from falign.extraction.frame_extractor import FrameExtractor

    frames = [
        {"image": "a.png", "action": "walk", "anchor": {"root": {"x": 1, "y": 2}}},
        {"id": 7, "image": "b.png"},
    ]
    result = FrameExtractor().process(frames)

    assert len(result) == 2
    assert result[0]["id"] == 0
    assert result[1]["id"] == 7
    assert result[0]["action"] == "walk"
    assert result[0]["anchor"] == {"root": {"x": 1, "y": 2}}
    assert result[1].get("action") is None


@check("falign", "anchor detection returns stable keypoints per frame")
def _():
    from falign.anchor.anchor_detector import AnchorDetector

    anchors = AnchorDetector().detect(make_asset()["animation"]["frames"])

    assert len(anchors) == 4
    for anchor in anchors:
        assert set(("root", "feet", "center", "head")) <= set(anchor)
    assert anchors[0]["root"]["x"] == 32
    assert anchors[3]["root"]["x"] == 35
    assert anchors[0]["feet"]["y"] == 64


@check("falign", "phase alignment maps frames onto the motion phase track")
def _():
    from falign.phase.phase_alignment import PhaseAligner

    result = PhaseAligner().align(make_asset()["animation"]["frames"], [])

    assert result["action"] == "walk"
    assert result["aligned"] is True
    track = result["phase"]
    assert len(track) == 4
    assert track[0] == 0.0
    assert track[-1] == 1.0


@check("falign", "root motion correction fixes drift")
def _():
    from falign.motion.root_motion import RootMotionCorrector

    frames = make_asset()["animation"]["frames"]
    anchors = [{"root": {"x": 32 + index, "y": 60}} for index in range(4)]
    result = RootMotionCorrector().correct(frames, anchors)

    assert result["drift_corrected"] is True
    assert result["real_motion"] is False
    assert result["root_dx"] == 0
    assert result["root_dy"] == 0
    assert len(result["corrections"]) == 4


@check("falign", "root motion correction keeps real motion")
def _():
    from falign.motion.root_motion import RootMotionCorrector

    frames = make_asset()["animation"]["frames"]
    anchors = [{"root": {"x": 10 * index, "y": 60}} for index in range(4)]
    result = RootMotionCorrector().correct(frames, anchors)

    assert result["real_motion"] is True
    assert result["drift_corrected"] is False
    assert result["root_dx"] == 30


@check("falign", "temporal analysis outputs jitter score and smooth verdict")
def _():
    from falign.temporal.temporal_consistency import TemporalAnalyzer

    frames = [
        {"id": 0, "image": "a.png"},
        {"id": 1, "image": "b.png", "difference": 0.2},
        {"id": 2, "image": "c.png", "difference": 0.1},
    ]
    result = TemporalAnalyzer().analyze(frames)

    assert result["jitter_score"] == 0.15
    assert result["smooth"] is False
    assert result["differences"] == [0.2, 0.1]

    single = TemporalAnalyzer().analyze([{"id": 0, "image": "a.png"}])
    assert single["smooth"] is True
    assert single["jitter_score"] == 0.0


@check("falign", "animation evaluator writes the quality score")
def _():
    from falign.quality.animation_quality import AnimationEvaluator

    quality = AnimationEvaluator().evaluate(
        [{"root": {"x": 32, "y": 60}}],
        {"root_dx": 0, "root_dy": 0, "drift_corrected": True},
        {"jitter_score": 0.04},
    )

    assert quality["anchor_score"] == 1.0
    assert quality["motion_score"] == 1.0
    assert 0.0 < quality["temporal_score"] <= 1.0
    assert 0.0 < quality["overall"] <= 1.0


@check("falign", "FAlignEngine returns CreativeAsset-compatible output")
def _():
    from falign.pipeline.falign_engine import FAlignEngine

    result = FAlignEngine().process(make_asset()["animation"]["frames"])

    assert set(("frames", "anchor", "phase", "motion")) <= set(result["animation"])
    assert result["animation"]["phase"]["action"] == "walk"
    assert 0.0 < result["quality"]["animation"]["overall"] <= 1.0


@check("falign", "CreativeAssetAdapter writes animation + quality back")
def _():
    from adapters.creative_asset_adapter import CreativeAssetAdapter

    asset = make_asset()
    asset["animation"].pop("anchor", None)
    result = CreativeAssetAdapter().export_asset(asset)

    assert result["animation"]["anchor"]
    assert result["animation"]["motion"]["drift_corrected"] is True
    assert 0.0 < result["quality"]["animation"]["overall"] <= 1.0


# ---------------------------------------------------------------
# GImport (Phase 5)
# ---------------------------------------------------------------


@check("gimport", "manifest generator emits the asset ID card")
def _():
    from gimport.manifest.manifest_generator import ManifestGenerator

    manifest = ManifestGenerator().generate({"id": "hero001", "type": "character"})

    assert manifest["asset_id"] == "hero001"
    assert manifest["type"] == "character"
    assert manifest["resources"]["texture"] == "hero001.png"
    assert manifest["resources"]["animation"] == "hero001.anim"
    assert manifest["resources"]["prefab"] == "hero001.prefab"
    assert manifest["valid"] is True


@check("gimport", "manifest schema validation catches missing fields")
def _():
    from gimport.manifest.schema import validate_manifest

    verdict = validate_manifest({"type": "character", "resources": {}})
    assert verdict["valid"] is False
    assert "asset_id" in verdict["missing"]


@check("gimport", "atlas builder packs frames with layout rects")
def _():
    from gimport.atlas.sprite_atlas_builder import SpriteAtlasBuilder

    atlas = SpriteAtlasBuilder().build(make_asset(count=10))["atlas"]

    assert atlas["name"] == "mage001"
    assert atlas["image"] == "mage001_sprite_atlas.png"
    assert len(atlas["frames"]) == 10
    assert len(atlas["layout"]) == 10
    assert atlas["size"] == {"width": 512, "height": 128}
    assert atlas["layout"][9]["rect"] == {"x": 64, "y": 64, "w": 64, "h": 64}


@check("gimport", "animation clip generator emits unity and cocos clips")
def _():
    from gimport.animation.animation_clip_generator import AnimationClipGenerator

    generator = AnimationClipGenerator()
    asset = make_asset()

    unity = generator.generate(asset, "unity")["clip"]
    assert unity["name"] == "walk"
    assert unity["fps"] == 12
    assert unity["loop"] is True
    assert unity["frame_count"] == 4

    cocos = generator.generate(asset, "cocos")["animation"]
    assert cocos["name"] == "walk"
    assert cocos["duration"] == 0.33
    assert cocos["loop"] is True


@check("gimport", "prefab generator emits the character entity")
def _():
    from gimport.prefab.prefab_generator import PrefabGenerator

    prefab = PrefabGenerator().generate({"id": "hero001"})["prefab"]

    assert prefab["name"] == "hero001.prefab"
    assert prefab["root"] == "hero001"
    assert prefab["components"] == [
        "SpriteRenderer",
        "Animator",
        "Collider",
        "Script",
        "AnimationController",
    ]


@check("gimport", "engine adapters map resources to engine paths")
def _():
    from gimport.adapters.cocos_adapter import CocosAdapter
    from gimport.adapters.godot_adapter import GodotAdapter
    from gimport.adapters.unity_adapter import UnityAdapter

    asset = {"id": "hero001"}

    cocos = CocosAdapter().import_asset(asset)
    assert cocos["engine"] == "cocos"
    assert cocos["resources"]["atlas"] == "assets/atlas/hero001_sprite_atlas.plist"

    unity = UnityAdapter().import_asset(asset)
    assert unity["resources"]["Prefab"] == "Assets/Prefab/hero001.prefab"

    godot = GodotAdapter().import_asset(asset)
    assert godot["resources"]["scenes"] == "scenes/hero001.tscn"


@check("gimport", "runtime validator checks the full import result")
def _():
    from gimport.pipeline.gimport_engine import GImportEngine

    result = GImportEngine().process(make_asset(), "cocos")
    validation = result["validation"]

    assert validation["status"] == "success"
    assert validation["score"] == 1.0
    assert all(item["passed"] for item in validation["checks"])


@check("gimport", "GImportEngine end-to-end for cocos and unity")
def _():
    from gimport.pipeline.gimport_engine import GImportEngine

    engine = GImportEngine()
    asset = make_asset()

    for target in ("cocos", "unity"):
        result = engine.process(asset, target)
        assert result["manifest"]["asset_id"] == "mage001"
        assert result["animation"]["clip" if target == "unity" else "animation"]
        assert result["engine"]["engine"] == target
        assert result["validation"]["status"] == "success"


@check("gimport", "one-click export produces the game asset package")
def _():
    from gimport.exporter.one_click_export import OneClickExporter

    export = OneClickExporter().export(make_asset(), "cocos")

    assert export["package"].startswith("FireMage_cocos_")
    assert export["package"].endswith("_GameAsset.zip")
    assert export["engine"] == "cocos"
    assert export["contents"] == ["Character", "Animation", "Prefab", "Config"]
    assert export["result"]["validation"]["status"] == "success"


# ---------------------------------------------------------------
# Creative Agent (Phase 6)
# ---------------------------------------------------------------


@check("agent", "intent analyzer detects engine and static goals")
def _():
    from agent.planner.intent_analyzer import IntentAnalyzer

    analyzer = IntentAnalyzer()

    intent = analyzer.analyze("制作角色并导入Unity")
    assert intent["engine"] == "unity"
    assert intent["requires"]["engine_import"] is True
    # 动态规划（Phase 4）：未提到动画时不再强制 FAlign
    assert intent["requires"]["animation_alignment"] is False

    animated = analyzer.analyze("制作角色并导入Unity，再做一个攻击动画")
    assert animated["requires"]["animation_alignment"] is True

    static = analyzer.analyze("生成一张静态角色立绘")
    assert static["requires"]["animation_alignment"] is False

    assert analyzer.analyze("做一个cocos小怪")["engine"] == "cocos"


@check("agent", "planner emits capability-based task plans")
def _():
    from agent.planner.planner import Planner

    plan = Planner().plan("制作一个像素RPG火焰法师，带攻击动画，并导入Unity")
    capabilities = [task["capability"] for task in plan["tasks"]]

    assert capabilities == ["generation", "PReCon", "FAlign", "GImport"]
    assert plan["tasks"][3]["engine"] == "unity"

    # 动态规划：只调度目标声明过的能力，而不是固定五段流水线
    lean_plan = Planner().plan("制作一个像素RPG火焰法师")
    assert [task["capability"] for task in lean_plan["tasks"]] == ["generation", "PReCon"]

    static_plan = Planner().plan("生成一张静态图标")
    assert "FAlign" not in [task["capability"] for task in static_plan["tasks"]]


@check("agent", "capability registry resolves planner capabilities")
def _():
    from agent.capability.capability_registry import build_default_registry

    registry = build_default_registry()

    for name in ("generation", "PReCon", "FAlign", "GImport"):
        capability = registry.find(name)
        assert capability is not None
        assert capability.handler is not None


@check("agent", "task executor raises on unknown capability")
def _():
    from agent.executor.task_executor import TaskExecutor

    try:
        TaskExecutor().execute({"capability": "Nope"}, None)
    except LookupError:
        pass
    else:
        raise AssertionError("unknown capability accepted")


@check("agent", "task memory stores checkpoints, versions and errors")
def _():
    from agent.memory.task_memory import TaskMemory

    memory = TaskMemory()
    memory.save_goal("make hero")
    memory.save_checkpoint("task1", {"id": "hero001"})
    memory.record_error("task2", "boom")

    assert memory.completed_steps == ["task1"]
    assert memory.asset_versions[0]["asset"]["id"] == "hero001"
    assert memory.errors == [{"task": "task2", "message": "boom"}]

    task_id, snapshot = memory.latest_checkpoint()
    assert task_id == "task1"
    assert snapshot == {"id": "hero001"}

    snapshot["id"] = "mutated"
    assert memory.latest_checkpoint()[1]["id"] == "hero001"


@check("agent", "quality gate flags sections below threshold")
def _():
    from agent.monitor.quality_gate import QualityGate

    gate = QualityGate()

    # 无下游处理器 = 合法完成（Phase 4 决策，例如 2D 概念图任务）
    assert gate.check({})["status"] == "PASS"

    passing = gate.check(
        {
            "quality": {
                "pixel": {"overall": 0.94},
                "animation": {"overall": 0.95},
                "engine": {"overall": 0.96},
            }
        }
    )
    assert passing["status"] == "PASS"
    assert passing["retry"] == []

    failing = gate.check({"quality": {"pixel": {"overall": 0.5}, "animation": {"overall": 0.95}}})
    assert failing["status"] == "RETRY"
    assert failing["retry"] == ["pixel"]


@check("agent", "quality gate structure/timeline/performance dimensions")
def _():
    from agent.monitor.quality_gate import QualityGate

    gate = QualityGate()

    # 结构：manifest 一旦产出就必须带 asset_id（资产身份证）
    assert gate.check({})["checks"]["structure"]["verdict"] == "SKIP"
    no_id = gate.check({"manifest": {"name": "x"}})
    assert no_id["checks"]["structure"]["verdict"] == "FAIL"
    assert "structure" in no_id["retry"] and no_id["status"] == "RETRY"
    ok_id = gate.check({"manifest": {"asset_id": "hero001"}})
    assert ok_id["checks"]["structure"]["verdict"] == "PASS"
    assert ok_id["status"] == "PASS"

    # 时间轴：帧时长总和与 fps 推导周期矛盾 → FAIL
    bad = gate.check({"animation": {"fps": 10, "frames": [{"duration": 1.0}, {"duration": 1.0}]}})
    assert bad["checks"]["timeline"]["verdict"] == "FAIL"
    assert "timeline" in bad["retry"]
    good = gate.check({"animation": {"fps": 10, "frames": [{"duration": 0.1}, {"duration": 0.1}]}})
    assert good["checks"]["timeline"]["verdict"] == "PASS"
    hintless = gate.check({"animation": {"fps": 10, "frames": [{}, {}]}})
    assert hintless["checks"]["timeline"]["verdict"] == "PASS"

    # 性能：meta.performance 超预算 → FAIL（阈值与 release L4 同源）
    over = gate.check({"meta": {"performance": {"execution_ms": 130000}}})
    assert over["checks"]["performance"]["verdict"] == "FAIL"
    assert over["status"] == "RETRY"
    within = gate.check({"meta": {"performance": {"execution_ms": 1000, "peak_mb": 10}}})
    assert within["checks"]["performance"]["verdict"] == "PASS"


@check("agent", "json persistence recovers from corrupted main file via backup")
def _():
    import json
    import os
    import tempfile

    from studio.backend.history_service.service import HistoryStore
    from studio.backend.persistence import atomic_write_json, read_json_recover

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "store.json")

        atomic_write_json(path, [{"id": "a"}])
        assert read_json_recover(path) == [{"id": "a"}]

        # 第二次写入成功后，.bak 保存上一份好副本
        atomic_write_json(path, [{"id": "b"}])
        assert read_json_recover(path + ".bak") == [{"id": "a"}]

        # 主文件写一半截断 → 自动回退备份
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"truncated": ')
        assert read_json_recover(path) == [{"id": "a"}]

        # HistoryStore 全链路：损坏主文件不吞历史（最多丢最后一次写入）
        store_path = os.path.join(tmp, "history.json")
        store = HistoryStore(store_path)
        store.add({"task_id": "t1", "goal": "g"})
        store.add({"task_id": "t2", "goal": "g2"})
        with open(store_path, "w", encoding="utf-8") as handle:
            handle.write("{corrupted")
        revived = HistoryStore(store_path)
        assert [r["task_id"] for r in revived._records] == ["t1"]
        assert json.loads(open(store_path + ".bak", encoding="utf-8").read())[0]["task_id"] == "t1"


class ScriptedExecutor:

    def __init__(self, fail_engines=("unity",)):
        self.fail_engines = fail_engines
        self.calls = []

    def execute(self, task, asset):
        self.calls.append(task.get("engine"))
        if task.get("engine") in self.fail_engines:
            raise ValueError("engine failure")
        return asset


@check("agent", "recovery manager falls back from unity to cocos")
def _():
    from agent.recovery.recovery_manager import RecoveryManager

    executor = ScriptedExecutor()
    asset, recovery = RecoveryManager(max_retries=1).recover(
        {"id": "t1", "capability": "GImport", "engine": "unity"},
        ValueError("first failure"),
        executor,
        {"id": "hero001"},
    )

    assert asset == {"id": "hero001"}
    assert recovery["strategy"] == "fallback"
    assert "cocos" in executor.calls


@check("agent", "recovery manager escalates to human-in-loop")
def _():
    from agent.recovery.recovery_manager import RecoveryManager

    asset, recovery = RecoveryManager(max_retries=1).recover(
        {"id": "t1", "capability": "GImport", "engine": "unity"},
        ValueError("first failure"),
        ScriptedExecutor(fail_engines=("unity", "cocos")),
        {"id": "hero001"},
    )

    assert asset is None
    assert recovery["strategy"] == "human-in-loop"
    assert "reason" in recovery


@check("agent", "workflow engine completes plans and resumes from checkpoints")
def _():
    from agent.planner.planner import Planner
    from agent.workflow.workflow_engine import WorkflowEngine

    workflow = WorkflowEngine()
    # 动态规划：断言 engine.target 需要在目标里显式请求引擎导入
    plan = Planner().plan("制作一个像素RPG火焰法师，并导入Cocos")

    first = workflow.run(plan)
    assert first["workflow"]["state"] == "success"
    assert all(step["status"] == "success" for step in first["workflow"]["steps"])
    assert first["asset"]["engine"]["target"] == "cocos"

    resumed = workflow.run(plan, resume=True)
    assert resumed["workflow"]["state"] == "success"
    assert all(step["status"] == "skipped" for step in resumed["workflow"]["steps"])
    assert resumed["asset"]["id"] == first["asset"]["id"]


@check("agent", "CreativeAgent.run returns the full production record")
def _():
    from agent.creative_agent import CreativeAgent

    result = CreativeAgent().run(
        "创建一个像素风RPG火焰法师角色，包含待机、攻击动画，并导入Cocos项目"
    )

    assert result["workflow"]["state"] == "success"
    capabilities = [task["capability"] for task in result["plan"]["tasks"]]
    assert capabilities == ["generation", "PReCon", "FAlign", "GImport"]

    asset = result["asset"]
    assert asset["pixel"]["grid"]["confidence"] > 0
    assert asset["animation"]["anchor"]
    assert asset["engine"]["target"] == "cocos"
    assert result["quality"]["status"] == "PASS"
    assert len(result["memory"]["completed_steps"]) == 4


# ---------------------------------------------------------------
# Multi-Agent System (Phase 7)
# ---------------------------------------------------------------


@check("multi-agent", "agent messages serialize and the bus routes them")
def _():
    from protocol.message import AgentMessage, MessageBus

    message = AgentMessage("ArtAgent", "AnimationAgent", "ASSET_READY", {"asset_id": "mage001"})
    assert message.to_dict() == {
        "from": "ArtAgent",
        "to": "AnimationAgent",
        "type": "ASSET_READY",
        "payload": {"asset_id": "mage001"},
    }

    bus = MessageBus()
    bus.register("ArtAgent")
    bus.register("AnimationAgent")
    bus.send(message)
    bus.send(AgentMessage("ArtAgent", "ArtAgent", "TASK_RESULT"))

    assert len(bus.receive("AnimationAgent")) == 1
    assert bus.receive("AnimationAgent") == []
    assert len(bus.receive("ArtAgent")) == 1
    assert len(bus.history) == 2


@check("multi-agent", "agent state machine rejects invalid transitions")
def _():
    from protocol.state import AgentState

    state = AgentState()
    assert state.to_dict()["state"] == "CREATED"
    state.transition("RUNNING")
    state.transition("SUCCESS")
    assert state.history == ["CREATED", "RUNNING", "SUCCESS"]

    broken = AgentState()
    try:
        broken.transition("WARP")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid state accepted")


@check("multi-agent", "supervisor planner assigns specialist agents")
def _():
    from agents.supervisor.planner import SupervisorPlanner

    plan = SupervisorPlanner().plan("生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")

    assignments = [(task["agent"], task["action"]) for task in plan["tasks"]]
    assert assignments == [
        ("ArtAgent", "create_character"),
        ("ArtAgent", "pixel_reconstruction"),
        ("AnimationAgent", "create_animation"),
        ("EngineAgent", "export_unity"),
    ]
    assert plan["intent"]["engine"] == "unity"


@check("multi-agent", "task router dispatches and rejects unknown agents")
def _():
    from agents.art_agent.art_agent import ArtAgent
    from agents.supervisor.task_router import TaskRouter

    router = TaskRouter()
    router.register(ArtAgent())

    try:
        router.route({"agent": "GhostAgent", "action": "boo"})
    except LookupError:
        pass
    else:
        raise AssertionError("unknown agent accepted")

    try:
        router.route({"agent": "ArtAgent", "action": "boo"})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown action accepted")

    asset = router.dispatch(
        {"agent": "ArtAgent", "action": "create_character", "goal": "火焰法师"}, None
    )
    assert asset["id"] == "mage001"


@check("multi-agent", "each specialist agent handles its own actions")
def _():
    from agents.animation_agent.animation_agent import AnimationAgent
    from agents.art_agent.art_agent import ArtAgent
    from agents.engine_agent.engine_agent import EngineAgent
    from agents.memory_agent.memory_agent import MemoryAgent
    from agents.qa_agent.qa_agent import QAAgent

    art = ArtAgent()
    assert art.can_handle("create_character")
    asset = art.handle({"action": "create_character", "goal": "火焰法师Boss"}, None)
    pixel_asset = art.handle({"action": "pixel_reconstruction"}, asset)
    assert pixel_asset["pixel"]["grid"]["size"] == 8

    animation = AnimationAgent().handle({"action": "create_animation"}, pixel_asset)
    assert animation["animation"]["anchor"]

    engine = EngineAgent()
    assert engine.can_handle("export_unity")
    assert engine.can_handle("export_godot")
    engine_asset = engine.handle({"action": "export_unity"}, animation)
    assert engine_asset["engine"]["target"] == "unity"

    qa_asset = QAAgent().handle({"action": "quality_check"}, engine_asset)
    assert qa_asset["quality"]["report"]["status"] in ("PASS", "RETRY", "PENDING")

    memory_asset = MemoryAgent().handle(
        {"action": "save_checkpoint", "id": "M01", "goal": "demo"}, qa_asset
    )
    assert memory_asset["memory"]["user_style"]["style"] == "pixel"


@check("multi-agent", "supervisor hands off assets between agents")
def _():
    from agents.supervisor.supervisor import SupervisorAgent

    result = SupervisorAgent().run("生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")

    types = [message["type"] for message in result["messages"]]
    assert types.count("ASSET_READY") >= 2
    assert "QUALITY_REPORT" in types

    handoffs = [message for message in result["messages"] if message["type"] == "ASSET_READY"]
    assert handoffs[0]["from"] == "ArtAgent"
    assert handoffs[0]["to"] == "AnimationAgent"


@check("multi-agent", "supervisor runs QA, repair and memory checkpoint")
def _():
    from agents.supervisor.supervisor import SupervisorAgent

    result = SupervisorAgent().run("生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")

    supervisor = result["supervisor"]
    assert supervisor["status"] == "PASS"
    assert all(step["status"] in ("success", "recovered") for step in supervisor["steps"])

    asset = result["asset"]
    assert asset["quality"]["report"]["status"] == "PASS"
    assert asset["memory"]["checkpoint"]["goal"].startswith("生成")
    assert asset["memory"]["user_style"]["engine"] == "unity"
    assert asset["engine"]["target"] == "unity"
    assert asset["pixel"]["palette"]["max_colors"] == 16


@check("multi-agent", "supervisor end-to-end produces an engine-ready asset")
def _():
    from agents.supervisor.supervisor import SupervisorAgent

    result = SupervisorAgent().run(
        "创建一个像素风RPG火焰法师角色，包含待机、攻击动画，并导入Cocos项目"
    )

    asset = result["asset"]
    assert result["supervisor"]["status"] == "PASS"
    assert asset["id"] == "mage001"
    assert asset["pixel"]["grid"]["confidence"] > 0
    assert asset["animation"]["phase"]["aligned"] is True
    assert asset["animation"]["motion"]["drift_corrected"] is True
    assert asset["engine"]["manifest"]["valid"] is True
    assert asset["engine"]["validation"]["status"] == "success"
    assert asset["quality"]["report"]["status"] == "PASS"


@check("architecture", "legacy systems stay deleted (no imports from backend/ or frontend/)")
def _():
    """Q4 4.2 遗留处置：backend/（Phase 11-23 旧后端）与 frontend/（MVP）已冻结并
    于 2026-10-05 整体删除（docs/legacy-inventory.md）。门禁保留，防止从 git 历史
    找回代码时把对已删系统的 import 重新带回活跃目录。"""
    import os
    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pattern = re.compile(
        r"^\s*(?:from|import)\s+(?:backend|frontend)\b",
        re.MULTILINE,
    )
    offenders = []
    for top in ("agent", "agents", "artgen", "adapters", "studio", "tests"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(dirpath, filename)
                with open(path, encoding="utf-8") as handle:
                    if pattern.search(handle.read()):
                        offenders.append(os.path.relpath(path, root))
    assert not offenders, "frozen legacy imports in: {}".format(offenders[:5])


@check("video-quality", "synthetic pipeline meets baseline gates (V1 spec + quality metrics)")
def _():
    """V4 门禁固化：视频转换管线（i2v mp4 → 抽帧选帧 → 合成循环动画）
    的交付规格与质量指标必须不低于 benchmark/video_baseline.json。

    基线是确定性合成视频跑出的（零额度、零网络）；采样参数变更需重录
    基线（video_quality.py 头部指纹注释的既有规程）。任一 TOLERANCES
    硬门失败（含 delivery_size / source_fps / mp4_width / mp4_fps /
    mp4_duration 五项交付规格门）即回归。"""

    import json

    import benchmark.video_quality as vq
    from studio.backend.animation_service.service import (
        VIDEO_SAMPLE_DURATION,
        VIDEO_SAMPLE_MIN_COUNT,
    )

    metrics = vq.run_pipeline(VIDEO_SAMPLE_MIN_COUNT, VIDEO_SAMPLE_DURATION)
    with open(vq.BASELINE_PATH, encoding="utf-8") as handle:
        baseline = json.load(handle)["baseline"]
    rows, failures, _loop_ratio = vq.compare(baseline, {"metrics": metrics})
    assert not failures, "video quality regression: {}".format("、".join(failures))
    assert baseline.get("metrics", {}).get("mp4_width"), (
        "baseline lacks mp4 delivery spec — re-record baseline (benchmark/video_quality.py)"
    )


@check("motion-quality", "procedural action chain meets baseline gates (V3.5 三维量化)")
def _():
    """V3.5 门禁固化：骨骼动作链的**动作流畅度 / 动作辨识度 / 细节还原**
    三维量化指标不得低于 benchmark/motion_baseline.json（离线确定性夹具，
    零额度零网络）。基线由 benchmark/motion_quality.py --record 录制；
    夹具/评分锚点/混合参数变更会使指纹失配，需重录基线。任一 TOLERANCES
    硬门或关键姿态特征（attack 命中前倾/武器扫掠/walk 抬脚交替/run 膝幅）
    失败即回归。"""

    import json

    import benchmark.motion_quality as mq

    metrics = mq.run_evaluation(blend=True)
    with open(mq.BASELINE_PATH, encoding="utf-8") as handle:
        doc = json.load(handle)
    assert doc.get("fingerprint") == mq.FINGERPRINT, (
        "motion baseline fingerprint mismatch — re-record baseline"
        " (benchmark/motion_quality.py --record)"
    )
    _rows, failures = mq.compare(doc["baseline"], metrics)
    assert not failures, "motion quality regression: {}".format("、".join(failures))


@check("model-service", "image soften pass neutralizes IP names for moderation retry")
def _():
    """生图审核二轮重试的前置：_soften_prompt 必须把知名 IP 角色名（哆啦A梦
    等平台风控头号诱因）改写为视觉特征描述、攻击性词汇中性化，并追加合规
    尾缀；对无 IP 文本同样安全（只加尾缀不误伤）。改写失败 = 「哆啦A梦」
    类输入在审核拦截后无自愈能力（runtime._call_external 会退回离线示意）。"""

    from studio.backend.model_service.service import _soften_prompt

    softened = _soften_prompt("蓝胖子哆啦A梦，圆滚滚身体，大眼睛，attack pose with sword")
    assert "哆啦A梦" not in softened, "IP name survived soften: {}".format(softened[:80])
    assert "圆滚滚机器猫" in softened, "IP replaced without visual traits preserved"
    assert "attack" not in softened and "sword" not in softened, "attack verbs survived soften"
    assert "Family-friendly" in softened, "compliance suffix missing"
    plain = _soften_prompt("一只普通的橘猫，站在草地上")
    assert "橘猫" in plain and "普通的" in plain, "soften must not mangle safe text"
    assert plain.endswith("no realistic harm.") or "Family-friendly" in plain


@check("model-service", "hard IP names are proactively neutralized (no suffix)")
def _():
    """D 主动 IP 中性化：现代版权角色（哆啦A梦/皮卡丘等平台必拦项）在送
    模型前就被替换为视觉特征且**不追加**合规尾缀（保持提示词干净）；古典
    人物（孙悟空）不在主动档——保留原文，由审核拦截后的安全改写轮兜底。"""

    from studio.backend.model_service.service import _soften_prompt, neutralize_hard_ip

    out = neutralize_hard_ip("哆啦A梦站在草地上")
    assert "哆啦A梦" not in out and "机器猫" in out, "hard IP not neutralized"
    assert "Family-friendly" not in out, "proactive pass must not append compliance suffix"
    untouched = neutralize_hard_ip("孙悟空与一只橘猫")
    assert "孙悟空" in untouched, "classical figure must stay verbatim in proactive pass"
    softened = _soften_prompt("孙悟空与皮卡丘同框")
    assert "皮卡丘" not in softened and "电气鼠" in softened, "soft round misses hard IP"
    assert "孙悟空" not in softened and "猴王" in softened, "soft round misses soft IP"


@check("model-service", "image failure guidance explains reason and defaults to strict")
def _():
    """生图失败策略契约：默认 strict（自救轮后仍失败→任务失败返回指引，
    绝不静默降级离线示意）；指引信息必须包含具体原因、已尝试动作与可操作
    的下一步（改描述/历史重试/开降级开关），按错误分类给出对应建议。"""

    from studio.backend.model_service.service import ModelSettingsStore, image_failure_guidance

    assert ModelSettingsStore._DEFAULTS.get("image_fallback_policy") == "strict", (
        "default policy must be strict — silent degrade is exactly the bug being fixed"
    )
    moderation = image_failure_guidance(
        {"kind": "moderation", "detail": "内容审核未通过（源图或提示词触发平台风控）"}
    )
    for keyword in ("AI 生图失败", "改写", "历史记录", "自动降级", "外观特征"):
        assert keyword in moderation, "moderation guidance missing: {}".format(keyword)
    quota = image_failure_guidance({"kind": "quota", "detail": "额度不足"})
    assert "Key" in quota and "重试" in quota, "quota guidance missing actionable steps"
    auth = image_failure_guidance({"kind": "auth", "detail": "鉴权失败"})
    assert "模型设置" in auth, "auth guidance should point to settings"


@check("agent", "image prompt hygiene strips engine clauses and expands bare goals")
def _():
    """C 提示词整备：goal 里的「并导入Unity」类工程子句不得进入画图提示词
    （引擎是结构化字段，不是画面语义）；超短目标（<8 字符）自动补构图
    扩写，让「法师」这类裸词也有可用的呈现方向；正常长度目标不受影响。"""

    from agent.generation.external import build_image_prompt

    stripped = build_image_prompt("生成一个法师，并导入Unity", None, None, style="pixel")
    assert "导入" not in stripped and "Unity" not in stripped, "engine clause leaked into prompt"
    assert "像素风游戏素材" in stripped, "style tail missing"
    bare = build_image_prompt("法师", None, None, style=None)
    assert "全身立绘" in bare, "bare goal not expanded"
    rich = build_image_prompt("穿深蓝长袍的白发老法师，手持星纹法杖，立于浮空符文阵上", None, None, style=None)
    assert "全身立绘" not in rich, "rich goal must not be expanded"


def main():
    failures = []
    current_group = None

    for group, name, func in CHECKS:
        if group != current_group:
            print("== {} ==".format(group))
            current_group = group
        try:
            func()
        except AssertionError as error:
            failures.append((group, name, str(error)))
            print("  FAIL {}".format(name))
            if str(error):
                print("       {}".format(error))
        except Exception as error:
            failures.append((group, name, "{}: {}".format(type(error).__name__, error)))
            print("  ERROR {} ({}: {})".format(name, type(error).__name__, error))
        else:
            print("  ok   {}".format(name))

    total = len(CHECKS)
    print()
    print("{} checks, {} failed".format(total, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
