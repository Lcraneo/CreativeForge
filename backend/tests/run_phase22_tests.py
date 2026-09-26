"""Phase 22 E2E verification (advanced agent platform), no pytest dependency:

    dynamic planner (style -> minimal chain) / StyleAgent palette carry /
    asset context retriever / confidence self-evaluation + low-confidence
    self-healing / MCP manifest + invoke / projects + role-guarded asset
    lifecycle + tenant scoping

Run: python backend/tests/run_phase22_tests.py
"""

import asyncio
import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_phase22_test.db")
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
    from app.main import app
    from app.runtime.agents.struct import AssetStructAgent
    from app.runtime.executor import get_executor
    from app.runtime.gateway import get_gateway

    await init_models()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # -- baseline character (full creation chain) ------------------------
        first = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "创建一个赛博朋克机械猫战士，装备火焰剑，有攻击动画，导入Cocos",
                  "user_id": "p22"},
        )
        body = first.json()
        asset_id = body["asset_id"]
        check("create baseline", first.status_code == 200 and asset_id)
        steps = body["result"]["quality_check"] and (
            (await client.get(f"/api/v1/tasks/{body['task_id']}")).json()["steps"] or []
        )
        check("steps carry confidence",
              steps and all(
                  isinstance(s.get("summary"), dict) and "confidence" in s["summary"]
                  for s in steps if s["status"] in ("done", "healed")
              ), str([(s["node"], s["summary"].get("confidence")) for s in steps]))

        # -- Phase 22.1: dynamic planner, style -> minimal chain --------------
        style_edit = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "给机械猫战士换个红色配色试试", "user_id": "p22"},
        )
        style_body = style_edit.json()
        plan = style_body["plan"]
        check("style intent change",
              plan["intent"]["change"] == "style"
              and plan["mode"] == "modify_existing_character", str(plan.get("change")))
        check("style short chain tasks",
              plan["tasks"] == ["find_character", "modify_style"], str(plan["tasks"]))
        agents_in_dag = {n["agent"] for n in plan["dag"]["nodes"]}
        check("style chain agents",
              {"MemoryAgent", "StyleAgent", "QualityAgent"} == agents_in_dag,
              str(sorted(agents_in_dag)))
        check("planner records the decision",
              any("minimal chain" in d for d in plan["decisions"]),
              str(plan["decisions"]))
        check("style edit completed",
              style_body["status"] == "completed", str(style_body.get("status")))

        result = style_body["result"]
        style_step = result.get("modify_style") or {}
        check("style edit versioned",
              style_step.get("version") == "v2"
              and "#e23b3b" in (style_step.get("palette") or []),
              str(style_step))
        check("regenerated stages skipped",
              "generate_asset" not in result and "motion_align" not in result
              and "combat" not in result, str(sorted(result)))
        check("identity similarity assessed",
              isinstance(style_step.get("identity_similarity"), (int, float))
              and style_step["identity_similarity"] > 0,
              str(style_step.get("identity_similarity")))

        style_detail = (
            await client.get(f"/api/v1/assets/{style_body['asset_id']}")
        ).json()["metadata_json"]
        check("style asset carries previous payload",
              (style_detail["animation"].get("clips") or [])
              and (style_detail["combat"].get("skills") or [])
              and style_detail["engine"]["target"] == "cocos",
              str(sorted(style_detail)))
        palette = (style_detail["pixel"]["palette"] or {}).get("colors") or []
        check("palette recolored", "#e23b3b" in palette, str(palette))
        check("style version lineage",
              style_detail["dna"]["version"] == "v2"
              and style_detail["dna"]["versions"] == ["v1", "v2"],
              str(style_detail["dna"].get("versions")))

        # -- weapon edit keeps the full pipeline ------------------------------
        weapon_edit = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "给机械猫战士换一把更长的火焰剑", "user_id": "p22"},
        )
        weapon_plan = weapon_edit.json()["plan"]
        weapon_nodes = {n["id"] for n in weapon_plan["dag"]["nodes"]}
        check("weapon edit keeps full chain",
              "motion_align" in weapon_plan["tasks"]
              and {"combat", "quality_check"} <= weapon_nodes
              and "modify_style" not in weapon_plan["tasks"],
              str(weapon_plan["tasks"]))

        # -- Phase 22.3: MCP tool ecosystem ------------------------------------
        manifest = (await client.get("/api/v1/mcp/tools")).json()
        tool_names = {t["name"]: t for t in manifest["tools"]}
        check("mcp manifest pipeline tools",
              tool_names["generate_asset"]["invocable"] is False
              and tool_names["modify_style"]["invocable"] is False,
              str(sorted(tool_names)))
        check("mcp manifest standalone tools",
              tool_names["export_cocos"]["invocable"] is True
              and tool_names["dna_embed"]["invocable"] is True
              and manifest["engines"] == ["cocos", "godot", "unity"],
              str(manifest["engines"]))

        invoke = await client.post(
            "/api/v1/mcp/invoke",
            json={"tool": "export_unity", "input": {"asset_id": asset_id}},
        )
        invoke_body = invoke.json()
        check("mcp invoke export_unity",
              invoke.status_code == 200
              and invoke_body["result"]["engine"] == "unity"
              and any("prefab/" in f for f in invoke_body["result"]["files"]),
              str(invoke_body)[:200])
        embed = await client.post(
            "/api/v1/mcp/invoke",
            json={"tool": "dna_embed", "input": {"image": "robot_cat.png"}},
        )
        check("mcp invoke dna_embed",
              embed.status_code == 200
              and len(embed.json()["result"]["vector"]) == 64,
              str(embed.json())[:120])
        unknown = await client.post(
            "/api/v1/mcp/invoke", json={"tool": "generate_asset", "input": {}}
        )
        check("mcp rejects pipeline tools",
              unknown.status_code == 404, str(unknown.status_code))

        # -- Phase 22.6/22.8: collaboration + tenancy ---------------------------
        project = (await client.post(
            "/api/v1/projects",
            json={"name": "Neon Cats", "owner_id": "alice", "tenant_id": "t1"},
        )).json()
        check("project created", bool(project.get("id")), str(project))

        bob = await client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"user_id": "bob", "role": "designer"},
        )
        carol = await client.post(
            f"/api/v1/projects/{project['id']}/members",
            json={"user_id": "carol", "role": "reviewer"},
        )
        check("members added", bob.status_code == 200 and carol.status_code == 200)

        attach = await client.post(
            f"/api/v1/projects/{project['id']}/assets",
            json={"asset_id": asset_id},
        )
        check("asset attached", attach.status_code == 200
              and attach.json()["status"] in ("ready", "created"), str(attach.json()))

        submit = await client.post(
            f"/api/v1/projects/{project['id']}/assets/{asset_id}/transition",
            json={"action": "submit", "user_id": "bob"},
        )
        check("designer submits review",
              submit.status_code == 200 and submit.json()["status"] == "in_review",
              str(submit.json()))

        denied = await client.post(
            f"/api/v1/projects/{project['id']}/assets/{asset_id}/transition",
            json={"action": "approve", "user_id": "bob"},
        )
        check("designer cannot approve", denied.status_code == 403, str(denied.status_code))

        approve = await client.post(
            f"/api/v1/projects/{project['id']}/assets/{asset_id}/transition",
            json={"action": "approve", "user_id": "carol"},
        )
        check("reviewer approves",
              approve.status_code == 200 and approve.json()["status"] == "approved",
              str(approve.json()))

        promote_denied = await client.post(
            f"/api/v1/projects/{project['id']}/assets/{asset_id}/transition",
            json={"action": "promote", "user_id": "carol"},
        )
        check("reviewer cannot promote",
              promote_denied.status_code == 403, str(promote_denied.status_code))

        outsider = await client.post(
            f"/api/v1/projects/{project['id']}/assets/{asset_id}/transition",
            json={"action": "promote", "user_id": "dave"},
        )
        check("non-member rejected", outsider.status_code == 403, str(outsider.status_code))

        promote = await client.post(
            f"/api/v1/projects/{project['id']}/assets/{asset_id}/transition",
            json={"action": "promote", "user_id": "alice"},
        )
        check("owner promotes to production",
              promote.status_code == 200 and promote.json()["status"] == "production",
              str(promote.json()))

        invalid = await client.post(
            f"/api/v1/projects/{project['id']}/assets/{asset_id}/transition",
            json={"action": "submit", "user_id": "alice"},
        )
        check("invalid transition 409", invalid.status_code == 409, str(invalid.status_code))

        detail = (await client.get(f"/api/v1/projects/{project['id']}")).json()
        check("project detail aggregates",
              {"alice": "owner", "bob": "designer", "carol": "reviewer"}.items()
              <= {m["user_id"]: m["role"] for m in detail["members"]}.items()
              and detail["assets"][0]["status"] == "production",
              str(detail)[:200])

        other_tenant = (await client.get(
            "/api/v1/projects", params={"tenant_id": "t2"}
        )).json()
        check("tenant scoping", other_tenant == [], str(other_tenant))

        # -- Phase 22.4: low-confidence self healing (stubbed agent) ----------
        executor = get_executor()
        real_struct = executor.agents["structure_asset"]
        state = {"calls": 0}

        class ShakyStruct(AssetStructAgent):
            async def run(self, context):
                state["calls"] += 1
                if state["calls"] == 1:
                    return {"layers": ["body"], "segmentation_score": 0.5}
                return await real_struct.run(context)

        executor.agents["structure_asset"] = ShakyStruct()
        try:
            async with AsyncSessionLocal() as db:
                healed = await get_gateway().submit(
                    "创建一个机械猫战士，导入godot", db, user_id="healer22",
                    engine="godot",
                )
            check("low-confidence healed", healed["status"] == "completed",
                  str(healed.get("status")))
            struct_summary = healed["result"].get("structure_asset", {})
            check("retry produced passing confidence",
                  state["calls"] == 2
                  and struct_summary.get("confidence", 1.0) >= 0.8,
                  f"calls={state['calls']}")
            trace = (await client.get(f"/api/v1/tasks/{healed['task_id']}")).json()
            eval_steps = [
                s for s in trace["steps"] or [] if s["node"] == "self_evaluation"
            ]
            check("self-evaluation step recorded",
                  len(eval_steps) == 1
                  and eval_steps[0]["summary"]["low_confidence"] == ["structure_asset"],
                  str(eval_steps))
        finally:
            executor.agents["structure_asset"] = real_struct

    failures = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
