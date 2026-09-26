"""Phase 21 E2E verification (product MVP), no pytest dependency:

    export.zip download (cocos / unity) / zip integrity + entries /
    placeholder PNG / DNA.json + skill.json payloads / POST /export
    regression / CORS for the frontend dev server

Run: python backend/tests/run_phase21_tests.py
"""

import asyncio
import io
import json
import os
import sys
import tempfile
import zipfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_phase21_test.db")
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
        goal = "创建一个赛博朋克机械猫战士，装备火焰剑，有攻击动画，导入Cocos"
        created = await client.post(
            "/api/v1/assets/create", json={"prompt": goal, "user_id": "p21"}
        )
        body = created.json()
        asset_id = body["asset_id"]
        check("create 200", created.status_code == 200 and asset_id)

        # -- Phase 21: zip download ----------------------------------------
        cross_origin = await client.get(
            "/health", headers={"Origin": "http://127.0.0.1:5173"}
        )
        check("cors open for frontend dev",
              cross_origin.headers.get("access-control-allow-origin")
              == "http://127.0.0.1:5173",
              str(dict(cross_origin.headers)))

        zipped = await client.get(f"/api/v1/assets/{asset_id}/export.zip")
        check("zip 200", zipped.status_code == 200, str(zipped.status_code))
        check("zip content type",
              zipped.headers.get("content-type") == "application/zip",
              str(zipped.headers.get("content-type")))
        check("zip filename header",
              "cocos_export.zip" in zipped.headers.get("content-disposition", ""),
              str(zipped.headers.get("content-disposition")))

        archive = zipfile.ZipFile(io.BytesIO(zipped.content))
        names = archive.namelist()
        check("zip has DNA.json", any(n.endswith("DNA.json") for n in names),
              str(names))
        check("zip has skill.json", any(n.endswith("skill.json") for n in names),
              str(names))
        check("zip has collider.json", any(n.endswith("collider.json") for n in names),
              str(names))
        textures = [n for n in names if "/textures/" in n and n.endswith(".png")]
        check("zip has texture", bool(textures), str(names))
        check("texture is a real png",
              bool(textures) and archive.read(textures[0]).startswith(b"\x89PNG\r\n\x1a\n"))
        check("zip has spriteframe",
              any("/spriteframes/" in n for n in names), str(names))
        check("zip has animation", any("/animations/" in n and n.endswith(".anim") for n in names))
        check("zip has prefab", any("/prefab/" in n and n.endswith(".prefab") for n in names))

        dna = json.loads(archive.read([n for n in names if n.endswith("DNA.json")][0]))
        check("DNA.json payload", bool(dna.get("character_id")), str(dna.get("character_id")))
        skill = json.loads(archive.read([n for n in names if n.endswith("skill.json")][0]))
        check("skill.json payload", skill.get("skill") == "fire_slash", str(skill))
        collider = json.loads(archive.read([n for n in names if n.endswith("collider.json")][0]))
        check("collider.json payload", bool(collider.get("hitboxes")), str(collider.get("hitboxes")))
        prefab = json.loads(archive.read(
            [n for n in names if n.endswith(".prefab")][0]))
        check("prefab colliders bound",
              bool(prefab.get("colliders", {}).get("hitbox")), str(prefab.get("colliders")))

        unity_zip = await client.get(
            f"/api/v1/assets/{asset_id}/export.zip", params={"engine": "unity"}
        )
        unity_names = zipfile.ZipFile(io.BytesIO(unity_zip.content)).namelist()
        check("unity zip via engine param",
              any("/prefab/" in n for n in unity_names)
              and any("/animator/" in n for n in unity_names), str(unity_names))

        export_api = await client.post(
            "/api/v1/assets/export", json={"asset_id": asset_id, "engine": "cocos"}
        )
        check("POST /export regression",
              export_api.status_code == 200
              and len(export_api.json()["files"]) > 0, str(export_api.status_code))

    failures = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
