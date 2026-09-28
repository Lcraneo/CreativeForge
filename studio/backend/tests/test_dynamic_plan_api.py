"""Phase 4 — /api/plan dynamic-plan endpoint (Studio, no server needed).

Run: python studio/backend/tests/test_dynamic_plan_api.py
"""

import asyncio
import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
for path in (REPO_ROOT, BACKEND_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("DB_PATH", os.path.join(tempfile.gettempdir(), "cf_plan_test.db"))

import httpx  # noqa: E402


async def main() -> int:
    from studio.backend.app import app

    transport = httpx.ASGITransport(app=app)
    ok = 0
    total = 0
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        total += 1
        response = await client.post("/api/plan", json={"goal": "生成像素弓箭手并导入 Unity"})
        caps = [t["capability"] for t in response.json().get("tasks", [])]
        if response.status_code == 200 and "GImport" in caps and "generation" in caps:
            print("[PASS] /api/plan returns dynamic capability plan", caps)
            ok += 1
        else:
            print("[FAIL] /api/plan", response.status_code, caps)

        total += 1
        static = await client.post("/api/plan", json={"goal": "创建一个 2D 动漫风机械 Boss"})
        caps2 = [t["capability"] for t in static.json().get("tasks", [])]
        if "FAlign" not in caps2 and "GImport" not in caps2:
            print("[PASS] 2D concept plan omits animation/engine", caps2)
            ok += 1
        else:
            print("[FAIL] 2D concept plan", caps2)

        total += 1
        empty = await client.post("/api/plan", json={"goal": "  "})
        if empty.status_code == 422:
            print("[PASS] empty goal rejected")
            ok += 1
        else:
            print("[FAIL] empty goal", empty.status_code)

    print(f"\n{ok}/{total} passed")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
