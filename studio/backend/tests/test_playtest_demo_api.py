"""Q3 3.1 — /api/playtest/previews guest/demo mode (Studio, no server needed).

不传 asset_id 必须返回完整可玩的演示条带（5 动作 × 8 帧，程序化引擎），
且整个路径只读、不触碰任何资产存储。

另覆盖 V2 渐进式加载参数（缺省=旧行为，向后兼容）：
- ?actions=idle,walk 只返回这两个动作；空/全部非法时回退全集；
- ?include_custom=0 被正常接受（guest 路径 custom_actions 恒为空）；
- 条带静态响应带 immutable 长缓存头（内容哈希命名，可零请求重访）。

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

        full_set = {"idle", "walk", "run", "attack", "jump"}

        # ── V2 参数：actions 过滤 ─────────────────────────────────
        total += 1
        response = await client.get("/api/playtest/previews", params={"actions": "idle,walk"})
        payload = response.json()
        filtered = (
            response.status_code == 200
            and set(payload.get("actions") or []) == {"idle", "walk"}
            and set(payload.get("strips") or {}) == {"idle", "walk"}
            and set(payload.get("previews") or {}) == {"idle", "walk"}
        )
        if filtered:
            print("[PASS] ?actions=idle,walk returns only the requested strips")
            ok += 1
        else:
            print("[FAIL] actions filter", response.status_code, payload.get("actions"))

        total += 1
        # 合法与非法混排：只保留合法部分（顺序按内置全集，不透传用户输入）
        response = await client.get(
            "/api/playtest/previews", params={"actions": "walk,bogus,idle"}
        )
        names = response.json().get("actions") or []
        mixed_ok = response.status_code == 200 and set(names) == {"idle", "walk"}
        if mixed_ok:
            print("[PASS] actions filter keeps valid names and drops unknown ones")
            ok += 1
        else:
            print("[FAIL] actions mixed filter", response.status_code, names)

        total += 1
        # 全部非法 → 回退全集（与缺省行为一致，不 422）
        response = await client.get("/api/playtest/previews", params={"actions": "bogus"})
        names = response.json().get("actions") or []
        fallback_ok = response.status_code == 200 and set(names) == full_set
        if fallback_ok:
            print("[PASS] all-invalid actions fall back to the full set")
            ok += 1
        else:
            print("[FAIL] actions fallback", response.status_code, names)

        total += 1
        # 空串 → 回退全集（"?actions=" 是前端拼接失败的常见形态）
        response = await client.get("/api/playtest/previews", params={"actions": ""})
        names = response.json().get("actions") or []
        empty_ok = response.status_code == 200 and set(names) == full_set
        if empty_ok:
            print("[PASS] empty actions param falls back to the full set")
            ok += 1
        else:
            print("[FAIL] empty actions param", response.status_code, names)

        # ── V2 参数：include_custom 门控（guest 路径恒空，仅验证接受参数）──
        total += 1
        response = await client.get(
            "/api/playtest/previews", params={"include_custom": "0"}
        )
        payload = response.json()
        custom_ok = response.status_code == 200 and payload.get("custom_actions") == []
        if custom_ok:
            print("[PASS] ?include_custom=0 accepted, custom_actions stays empty for guest")
            ok += 1
        else:
            print("[FAIL] include_custom=0", response.status_code, payload.get("custom_actions"))

        # ── 条带静态响应：immutable 长缓存头 ───────────────────────
        total += 1
        strip_url = (payload.get("previews") or {}).get("idle")
        response = await client.get(strip_url) if strip_url else None
        cache_ok = (
            response is not None
            and response.status_code == 200
            and response.headers.get("Cache-Control")
            == "public, max-age=31536000, immutable"
            and response.headers.get("Content-Type", "").startswith("image/png")
        )
        if cache_ok:
            print("[PASS] play_cache strip serves png with immutable cache header")
            ok += 1
        else:
            header = response.headers.get("Cache-Control") if response is not None else None
            print("[FAIL] strip cache header", strip_url, header)

    print(f"\n{ok}/{total} passed")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
