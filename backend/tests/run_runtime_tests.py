"""Runtime E2E verification (Phase 16-19), no pytest dependency:

    DAG planning / parallel execution / execution trace / agent_tasks
    combat skill / quality gate / six-layer DNA profile / identity
    similarity / review pause + approve resume / preference memory /
    healing retry / export API / animation library / quality model

Run: python backend/tests/run_runtime_tests.py
"""

import asyncio
import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_runtime_test.db")
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
    from app.core.database import AsyncSessionLocal, init_models
    from app.engines.foundation.animation_library import describe, resolve_action
    from app.engines.foundation.quality_model import assess_identity
    from app.main import app
    from app.runtime.agents.export import ExportAgent
    from app.runtime.executor import get_executor
    from app.runtime.gateway import get_gateway

    await init_models()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        goal = "创建一个赛博朋克机械猫战士，装备火焰剑，有攻击动画，导入Cocos"
        response = await client.post(
            "/api/v1/assets/create",
            json={"prompt": goal, "user_id": "tester"},
        )
        body = response.json()
        check("create 200", response.status_code == 200, str(response.status_code))

        # -- Phase 16: intent + DAG planning --------------------------------
        plan = body["plan"]
        intent = plan["intent"]
        check("intent type", intent["type"] == "game_character_creation", str(intent))
        check("intent requirements",
              {"character", "weapon", "combat"} <= set(intent["requirements"]),
              str(intent["requirements"]))
        check("intent engine cocos", intent["engine"] == "cocos")
        check("style decision recorded",
              any("cyberpunk" in d for d in plan["decisions"]), str(plan["decisions"]))

        dag = plan["dag"]
        edges = {tuple(edge) for edge in dag["edges"]}
        check("dag parallel branches",
              {("structure_asset", "create_dna"), ("structure_asset", "motion_align")}
              <= edges, str(sorted(edges)))
        check("dag convergence",
              {("create_dna", "combat"), ("motion_align", "combat")} <= edges,
              str(sorted(edges)))
        check("dag tail chain",
              {("combat", "gimport"), ("gimport", "quality_check")} <= edges)
        agents_in_dag = {node["agent"] for node in dag["nodes"]}
        check("dag domain agents",
              {"GenerateAgent", "AssetStructAgent", "DNAAgent", "MotionAgent",
               "CombatAgent", "ExportAgent", "QualityAgent"} <= agents_in_dag,
              str(sorted(agents_in_dag)))
        check("mcp capabilities", plan["capabilities"][0] == "generate_asset")

        # -- Phase 17: execution trace + agent task record -------------------
        result = body["result"]
        check("parallel branches executed",
              "create_dna" in result and "motion_align" in result, str(sorted(result)))
        check("combat skill emitted",
              result["combat"]["skill"] == "fire_slash"
              and result["combat"]["damage"] == 100, str(result.get("combat")))
        check("quality gate passed",
              result["quality_check"]["passed"] is True
              and result["quality_check"]["score"] > 0, str(result.get("quality_check")))

        task_id = body["task_id"]
        response = await client.get(f"/api/v1/tasks/{task_id}")
        task_body = response.json()
        check("agent task trace", task_body["source"] == "agent_task"
              and task_body["status"] == "completed", str(task_body["status"]))
        steps = task_body["steps"] or []
        check("steps carry agents+timing",
              all("agent" in s and "ms" in s for s in steps) and len(steps) >= 7,
              str(len(steps)))
        check("combat step is CombatAgent",
              any(s["agent"] == "CombatAgent" for s in steps))

        # -- Phase 19: DNA profile + identity similarity ----------------------
        asset_id = body["asset_id"]
        detail = (await client.get(f"/api/v1/assets/{asset_id}")).json()["metadata_json"]
        profile = (detail["dna"]["identity"] or {}).get("dna_profile") or {}
        check("six-layer dna profile",
              {"appearance", "style", "structure", "equipment", "motion", "combat"}
              <= set(profile), str(sorted(profile)))
        check("profile equipment weapon", profile["equipment"]["weapon"] is True)
        check("motion from library", profile["motion"]["primary_action"] == "attack"
              and profile["motion"]["semantic"] == "close melee attack")

        # -- Phase 14+19: identity-preserving edit with similarity ------------
        edit = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "给机械猫战士换一把火焰剑", "user_id": "tester"},
        )
        edit_body = edit.json()
        check("edit keeps identity",
              edit_body["result"]["create_dna"]["character_id"]
              == detail["dna"]["character_id"])
        edit_detail = (await client.get(f"/api/v1/assets/{edit_body['asset_id']}")).json()["metadata_json"]
        similarity = (edit_detail.get("dna") or {}).get("identity_similarity")
        check("identity similarity assessed",
              isinstance(similarity, (int, float)) and similarity > 0,
              str(similarity))

        # -- Phase 17.10: review pause + approve resume ------------------------
        review_resp = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "创建一个像素弓箭手，导入unity", "review": True,
                  "user_id": "tester"},
        )
        review_body = review_resp.json()
        check("pauses for concept review",
              review_body["status"] == "waiting_review"
              and review_body["review"]["type"] == "concept_review",
              str(review_body.get("status")))
        review_task_id = review_body["task_id"]
        check("no asset before approval", review_body["asset_id"] is None)

        approve = await client.post(f"/api/v1/tasks/{review_task_id}/approve")
        approve_body = approve.json()
        check("approve resumes to completion",
              approve.status_code == 200
              and approve_body["status"] == "completed"
              and approve_body["asset_id"], str(approve_body))
        resumed = (await client.get(f"/api/v1/tasks/{review_task_id}")).json()
        resumed_steps = resumed["steps"] or []
        check("resume keeps earlier steps",
              sum(1 for s in resumed_steps if s["node"] == "generate_asset") == 1,
              str([s["node"] for s in resumed_steps]))

        # -- Phase 17.8: preference memory -------------------------------------
        from sqlalchemy import select

        from app.models import UserPreference

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(UserPreference).where(UserPreference.user_id == "tester")
                )
            ).scalars()
            prefs = {row.key: (row.value or {}).get("value") for row in rows}
        check("preference memory persisted",
              "style" in prefs and "engine" in prefs, str(prefs))

        # -- Phase 18.10: export center ----------------------------------------
        export = await client.post(
            "/api/v1/assets/export",
            json={"asset_id": asset_id, "engine": "unity"},
        )
        export_body = export.json()
        check("export to unity", export.status_code == 200
              and export_body["engine"] == "unity", str(export_body))
        check("unity resource tree",
              any("prefab/" in f for f in export_body["files"])
              and any("animator/" in f for f in export_body["files"]),
              str(export_body["files"]))
        detail_after = (await client.get(f"/api/v1/assets/{asset_id}")).json()
        check("export persisted on asset",
              detail_after["metadata_json"]["engine"]["target"] == "unity")

        # -- Phase 19.11: animation library -------------------------------------
        check("library resolve attack", resolve_action(["attack"]) == "attack")
        check("library semantics", describe("attack")["semantic"] == "close melee attack"
              and describe("run")["difficulty"] == "easy")

    # -- Phase 17.11: self healing on a failing node (outside the app client) --
    executor = get_executor()
    real_export = executor.agents["gimport"]
    state = {"calls": 0}

    class FlakyExport(ExportAgent):
        async def run(self, context):
            state["calls"] += 1
            if state["calls"] == 1:
                raise RuntimeError("engine export crashed")
            return await real_export.run(context)

    executor.agents["gimport"] = FlakyExport()
    try:
        async with AsyncSessionLocal() as db:
            healed = await get_gateway().submit(
                "创建一个机械猫战士，导入godot", db, user_id="healer", engine="godot"
            )
        check("healed after retry", healed["status"] == "completed",
              str(healed.get("status")))
        check("retry actually happened", state["calls"] == 2, str(state))
        check("healed engine godot", healed["plan"]["engine"] == "godot")
    finally:
        executor.agents["gimport"] = real_export

    # -- Phase 19.12: quality model --------------------------------------------
    same = assess_identity(
        {"profile": {"palette": ["#111111", "#00c8ff"], "structure": {"height_ratio": 1.8},
                     "style": {"name": "cyberpunk"}}},
        {"profile": {"palette": ["#111111", "#00c8ff"], "structure": {"height_ratio": 1.8},
                     "style": {"name": "cyberpunk"}}},
    )
    check("same identity scores high", same["similarity"] > 0.9, str(same))
    other = assess_identity(
        {"profile": {"palette": ["#111111"], "structure": {"height_ratio": 1.8},
                     "style": {"name": "cyberpunk"}}},
        {"profile": {"palette": ["#ffaa00"], "structure": {"height_ratio": 0.9},
                     "style": {"name": "pixel"}}},
    )
    check("changed identity scores lower",
          other["similarity"] < same["similarity"], str(other))

    failures = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
