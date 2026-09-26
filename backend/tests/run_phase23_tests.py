"""Phase 23 E2E verification (research & innovation layer), no pytest:

    knowledge graph mining + API / skill edit chain (GameLogicAgent +
    SimulationAgent) / CreativeSkill blueprint (spec numbers) / simulation
    auto-repair / engine scripts / task-level evaluation / game creation
    benchmark / weapon regression

Run: python backend/tests/run_phase23_tests.py
"""

import asyncio
import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_phase23_test.db")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"

import httpx  # noqa: E402

CHECKS = []


def check(name: str, condition: bool, detail: str = ""):
    CHECKS.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not condition else ""))


async def main() -> int:
    from app.core.database import init_models
    from app.main import app

    await init_models()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # -- baseline character ------------------------------------------------
        first = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "创建一个赛博朋克机械猫战士，装备火焰剑，有攻击动画，导入Cocos",
                  "user_id": "p23"},
        )
        body = first.json()
        asset_id = body["asset_id"]
        check("create baseline", first.status_code == 200 and asset_id)

        # -- Phase 23.1-4: knowledge graph -------------------------------------
        graph = (await client.get("/api/v1/knowledge/graph")).json()
        types = {n["type"] for n in graph["nodes"]}
        labels = {n["label"] for n in graph["nodes"]}
        relations = {e["relation"] for e in graph["edges"]}
        check("graph mined from assets", graph["assets_mined"] >= 1, str(graph["assets_mined"]))
        check("graph node types",
              {"character", "weapon", "skill", "animation", "engine"} <= types,
              str(sorted(types)))
        check("graph has fire_slash skill", "fire_slash" in labels, str(sorted(labels)))
        check("graph relations",
              {"HAS_WEAPON", "TRIGGERS", "NEEDS", "HAS_ANIMATION", "EXPORTED_TO"}
              <= relations, str(sorted(relations)))

        # -- Phase 23.5-7: skill edit chain (dash = spec's exact example) -------
        dash_edit = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "给机械猫增加一个冲刺技能", "user_id": "p23"},
        )
        dash_body = dash_edit.json()
        plan = dash_body["plan"]
        check("skill intent change",
              plan["intent"]["change"] == "skill"
              and plan["mode"] == "modify_existing_character", str(plan.get("change")))
        check("skill chain tasks",
              plan["tasks"] == ["find_character", "create_logic", "simulate", "gimport"],
              str(plan["tasks"]))
        edges = {tuple(e) for e in plan["dag"]["edges"]}
        check("skill chain linear dag",
              {("find_character", "create_logic"), ("create_logic", "simulate"),
               ("simulate", "gimport"), ("gimport", "quality_check")} <= edges,
              str(sorted(edges)))
        check("planner records logic decision",
              any("logic chain" in d for d in plan["decisions"]), str(plan["decisions"]))
        check("skill edit completed", dash_body["status"] == "completed",
              str(dash_body.get("status")))

        # spec 七 example numbers: dash / cooldown 3 / damage 20 / blue_flash
        logic = dash_body["result"]["create_logic"]
        check("dash blueprint matches spec",
              logic["skill"] == "dash" and logic["cooldown"] == 3.0
              and logic["damage"] == 20 and logic["animation"] == "dash_attack"
              and logic["effect"] == "blue_flash", str(logic))
        simulation = dash_body["result"]["simulate"]
        check("dash passes simulation",
              simulation["passed"] is True and simulation["repairs"] == 0,
              str(simulation))

        detail = (
            await client.get(f"/api/v1/assets/{dash_body['asset_id']}")
        ).json()["metadata_json"]
        blueprint = (detail["logic"]["skills"] or [{}])[0]
        check("blueprint persisted with engine scripts",
              blueprint.get("name") == "dash"
              and "class DashSkill" in blueprint["engine"]["unity"]["code"]
              and blueprint["engine"]["cocos"]["events"][0]["handler"] == "on_dash",
              str(blueprint.get("engine"))[:120])
        combat_names = {s["skill"] for s in detail["combat"]["skills"]}
        check("combat skill list synced",
              {"fire_slash", "dash"} <= combat_names, str(sorted(combat_names)))
        check("skill version lineage",
              detail["dna"]["version"] == "v2"
              and detail["dna"]["versions"] == ["v1", "v2"],
              str(detail["dna"].get("versions")))

        graph_after = (await client.get("/api/v1/knowledge/graph")).json()
        logic_labels = {n["label"] for n in graph_after["nodes"] if n["type"] == "logic_skill"}
        check("graph grew logic skill node", "dash" in logic_labels, str(sorted(logic_labels)))

        # -- Phase 23.8-9: simulation auto-repair (fireball over damage cap) ----
        fire_edit = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "给机械猫增加一个火球技能", "user_id": "p23"},
        )
        fire_body = fire_edit.json()
        fire_logic = fire_body["result"]["create_logic"]
        check("fireball blueprint generated",
              fire_logic["skill"] == "fireball" and fire_logic["effect"] == "fire_burst",
              str(fire_logic))
        fire_sim = fire_body["result"]["simulate"]
        fire_issues = fire_sim.get("issues") or []
        check("overpowered damage auto-repaired",
              fire_sim["repairs"] >= 1
              and any(
                  i["check"] == "gameplay.damage_bounds" and i["before"] == 87.5
                  and i["after"] == 80 for i in fire_issues
              ), str(fire_issues))
        fire_detail = (
            await client.get(f"/api/v1/assets/{fire_body['asset_id']}")
        ).json()["metadata_json"]
        fire_bp = next(
            (s for s in fire_detail["logic"]["skills"] if s["name"] == "fireball"), {}
        )
        check("repaired damage persisted",
              fire_bp.get("damage") == 80
              and fire_detail["dna"]["version"] == "v3", str(fire_bp.get("damage")))

        # -- Phase 23.10: task evaluation record ---------------------------------
        trace = (await client.get(f"/api/v1/tasks/{fire_body['task_id']}")).json()
        evaluation = (trace.get("result") or {}).get("evaluation") or {}
        check("task evaluation recorded",
              {"identity", "animation", "engine", "overall"} <= set(evaluation)
              and evaluation["overall"] > 0.5, str(evaluation))
        confidences = [
            (s["summary"] or {}).get("confidence")
            for s in trace["steps"] or []
            if s["node"] in ("create_logic", "simulate")
        ]
        check("logic/simulate confidence >= 0.8",
              confidences and all(c is not None and c >= 0.8 for c in confidences),
              str(confidences))

        # -- Phase 23.13: game creation benchmark --------------------------------
        benchmark = (await client.post("/api/v1/benchmark/run")).json()
        check("benchmark assets scored",
              len(benchmark["assets"]) >= 2
              and all({"asset", "game", "overall"} <= set(a["scores"])
                      for a in benchmark["assets"]), str(len(benchmark["assets"])))
        agent = benchmark["agent"]
        check("benchmark agent score",
              agent["completion_rate"] == 1.0
              and agent["avg_confidence"] is not None, str(agent))
        check("cf score healthy", benchmark["cf_score"] >= 0.8, str(benchmark["cf_score"]))

        # -- weapon edit regression (full chain intact) ---------------------------
        weapon_edit = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "给机械猫战士换一把更长的火焰剑", "user_id": "p23"},
        )
        weapon_plan = weapon_edit.json()["plan"]
        check("weapon edit keeps full chain",
              "motion_align" in weapon_plan["tasks"]
              and "create_logic" not in weapon_plan["tasks"],
              str(weapon_plan["tasks"]))

    failures = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
