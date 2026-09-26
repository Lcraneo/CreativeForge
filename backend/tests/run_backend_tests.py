"""Backend E2E verification (no pytest dependency): boots the FastAPI app
in-process over a temp SQLite DB and walks the Phase 11-15 surface:

    health / create (new character) / create (identity-preserving edit)
    / asset detail / dna get / dna search / task record / engine units

Run: python backend/tests/run_backend_tests.py
"""

import asyncio
import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_backend_test.db")
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
        # -- health ------------------------------------------------------
        response = await client.get("/health")
        check("health 200", response.status_code == 200, str(response.status_code))

        # -- Phase 11-15: create a new character --------------------------
        goal = "创建一个机械猫战士，带火焰剑攻击，导入cocos"
        response = await client.post("/api/v1/assets/create", json={"prompt": goal})
        body = response.json()
        check("create 200", response.status_code == 200, str(response.status_code))

        plan = body["plan"]
        check("plan mode create_character", plan["mode"] == "create_character", str(plan))
        check("plan tasks full chain",
              plan["tasks"] == ["generate_asset", "structure_asset", "create_dna",
                                "motion_align", "gimport"], str(plan["tasks"]))
        check("plan engine cocos", plan["engine"] == "cocos", str(plan["engine"]))

        result = body["result"]
        check("generate returns image+style",
              result["generate_asset"]["image"].endswith(".png")
              and result["generate_asset"]["style"], str(result.get("generate_asset")))

        asset_id = body["asset_id"]
        check("asset_id returned", bool(asset_id))

        # -- asset detail: full CreativeAsset -----------------------------
        response = await client.get(f"/api/v1/assets/{asset_id}")
        detail = response.json()["metadata_json"]

        layers = detail["content"]["layers"]
        layer_names = [layer["name"] for layer in layers]
        check("asset layers body/weapon(+armor/effect)",
              "body" in layer_names and "weapon" in layer_names, str(layer_names))
        check("asset graph root character",
              detail["content"]["graph"]["id"] == "character")
        check("asset anchors", set(detail["visual"]["anchor_point"]) >= {"root", "hand", "feet"})
        check("pixel palette", len(detail["pixel"]["palette"]["colors"]) > 0)
        check("segmentation score", detail["quality"]["segmentation_score"] > 0.8)

        animation = detail["animation"]
        check("animation frames", len(animation["frames"]) == 8, str(len(animation["frames"])))
        check("animation action attack", animation["action"] == "attack")
        check("animation anchor root pinned",
              animation["anchor"]["root"] == {"x": 256.0, "y": 400.0})
        check("root residual ~0", animation["motion"]["max_root_residual"] < 1.0,
              str(animation["motion"]["max_root_residual"]))
        check("atlas packed 8 sprites",
              len(animation["atlas_detail"]["sprites"]) == 8)
        check("timeline fps 12", animation["timeline"]["fps"] == 12)
        event_types = [event["type"] for event in animation["timeline"]["events"]]
        check("hitbox events bound",
              "hitbox_enable" in event_types and "hitbox_disable" in event_types,
              str(event_types))
        check("states + graph", animation["states"]["current"] == "idle"
              and animation["graph"]["nodes"] == ["idle", "run", "attack"])

        combat = detail["combat"]
        check("hitbox polygon expanded",
              bool(combat["hitboxes"]) and len(combat["hitboxes"][0]["points"]) == 4)
        check("hurtbox from body layer", bool(combat["hurtboxes"]))

        engine = detail["engine"]
        check("engine target cocos", engine["target"] == "cocos")
        files = engine["resources"]["files"]
        check("cocos resource tree",
              any("textures/" in f for f in files)
              and any("spriteframes/" in f for f in files)
              and any("animations/" in f for f in files)
              and any("prefab/" in f for f in files), str(sorted(files)))

        dna = detail["dna"]
        character_id = dna["character_id"]
        check("dna created v1", dna["version"] == "v1", str(dna))
        check("identity semantics",
              dna["identity"]["role"] == "warrior" and dna["identity"]["species"] == "cat_robot",
              str(dna["identity"]))

        # -- Phase 14: identity-preserving modification --------------------
        edit_goal = "给机械猫战士换一把火焰剑"
        response = await client.post("/api/v1/assets/create", json={"prompt": edit_goal})
        edit_body = response.json()
        edit_plan = edit_body["plan"]
        check("edit plan mode modify", edit_plan["mode"] == "modify_existing_character",
              str(edit_plan))
        check("edit plan starts with find_character",
              edit_plan["tasks"][0] == "find_character", str(edit_plan["tasks"]))

        edit_result = edit_body["result"]
        check("find_character hit", edit_result["find_character"].get("found") is True,
              str(edit_result.get("find_character")))
        check("same character after edit",
              edit_result["create_dna"]["character_id"] == character_id,
              f"{edit_result.get('create_dna')} vs {character_id}")
        check("version bumped to v2", edit_result["create_dna"]["version"] == "v2")

        edit_asset = await client.get(f"/api/v1/assets/{edit_body['asset_id']}")
        edit_detail = edit_asset.json()["metadata_json"]
        check("edit image is versioned",
              edit_detail["content"]["image"].endswith("_v2.png"),
              edit_detail["content"]["image"])

        # -- DNA API -------------------------------------------------------
        response = await client.get(f"/api/v1/dna/{character_id}")
        dna_body = response.json()
        check("dna get 200", response.status_code == 200)
        check("dna versions lineage", dna_body["versions"] == ["v1", "v2"],
              str(dna_body["versions"]))

        response = await client.post("/api/v1/dna/search",
                                     json={"image": f"{character_id.rsplit('_', 1)[0]}_v9.png"})
        search_body = response.json()
        check("dna search same character",
              search_body["match"] == character_id and search_body["is_same_character"]
              and search_body["score"] > 0.85, str(search_body))

        response = await client.post("/api/v1/dna/search", json={"image": "totally_other.png"})
        other = response.json()
        check("dna search different character", not other["is_same_character"], str(other))

        # -- task record ----------------------------------------------------
        response = await client.get(f"/api/v1/tasks/{body['task_id']}")
        check("task persisted", response.status_code == 200
              and response.json()["status"] == "completed")

        # -- engine units ----------------------------------------------------
        from app.engines.gimport.exporter.registry import register_default_exporters
        exporters = register_default_exporters()
        check("unity exporter registered", "unity" in exporters.names())

        from app.engines.motion_align.timeline.state_machine import (
            AnimationStateMachine,
            default_states,
        )
        machine = AnimationStateMachine(default_states())
        machine.next({"move": True})
        check("state machine idle->run", machine.current.name == "run")
        machine.next({"attack": True})
        check("state machine run->attack", machine.current.name == "attack")

    failures = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
