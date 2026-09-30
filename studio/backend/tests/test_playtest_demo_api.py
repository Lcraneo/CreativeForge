"""Q3 3.1 — /api/playtest/previews guest/demo mode (Studio, no server needed).

不传 asset_id 必须返回完整可玩的演示条带（5 动作 × 8 帧，程序化引擎），
且整个路径只读、不触碰任何资产存储。

Run: python studio/backend/tests/test_playtest_demo_api.py
"""

import asyncio
import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
for path in (REPO_ROOT, BACKEND_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("DB_PATH", os.path.join(tempfile.gettempdir(), "cf_playtest_test.db"))

import httpx  # noqa: E402


async def main() -> int:
    from studio.backend.app import app

    transport = httpx.ASGITransport(app=app)
    ok = 0
    total = 0
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        total += 1
        response = await client.get("/api/playtest/previews")
        payload = response.json()
        actions = payload.get("actions") or []
        strips = payload.get("strips") or {}
        demo_ok = (
            response.status_code == 200
            and set(actions) >= {"idle", "walk", "run", "attack", "jump"}
            and all(name in strips for name in actions)
            and all(strips[name].get("frames", 0) >= 16 for name in actions)
            and all(strips[name].get("fps", 0) >= 16 for name in actions)
            and payload.get("fps", 0) >= 16
            and all(strips[name].get("engine") == "procedural" for name in actions)
        )
        if demo_ok:
            print("[PASS] guest demo previews: 5 actions, procedural strips @16f/16fps")
            ok += 1
        else:
            print(
                "[FAIL] guest demo previews",
                response.status_code,
                actions,
                {k: (v.get("frames"), v.get("fps"), v.get("engine")) for k, v in strips.items()},
            )

        total += 1
        # 演示路径是纯读：重复请求结果应稳定（无副作用累积）
        again = await client.get("/api/playtest/previews")
        same = again.status_code == 200 and again.json().get("actions") == actions
        if same:
            print("[PASS] demo previews are read-only and stable across calls")
            ok += 1
        else:
            print("[FAIL] demo previews changed across calls")

    print(f"\n{ok}/{total} passed")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
