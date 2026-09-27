"""Multi-provider image API extension — verification (no network / no GPU).

Covers the provider registry, request/response adapters, custom-provider CRUD,
credential handling, the built-in fallback strategy and the end-to-end asset
creation path (model name recorded on the task step + asset metadata).

Run: python backend/tests/run_providers_tests.py
"""

import asyncio
import os
import struct
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_providers_test.db")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"

import httpx  # noqa: E402

from app.engines.imagegen.providers import (  # noqa: E402
    PROVIDERS,
    PROVIDER_ORDER,
    build_request,
    parse_image,
)
from app.engines.imagegen.service import generate  # noqa: E402
from app.engines.imagegen.store import get_store  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not condition else ""))


def _png_size(data):
    return struct.unpack(">II", data[16:24])


async def main() -> int:
    from app.core.database import init_models
    from app.main import app

    await init_models()
    store = get_store()

    # -- registry --------------------------------------------------------
    listing = store.public_listing()
    ids = {p["id"] for p in listing["providers"]}
    check("builtin provider present", "builtin" in ids)
    for pid in PROVIDER_ORDER:
        check(f"preset {pid} registered", pid in ids)
    check("seven vendors pre-registered", len(PROVIDER_ORDER) == 7, str(PROVIDER_ORDER))
    check("default selection is builtin", listing["selected"]["provider"] == "builtin")
    check("providers expose models", all(p["models"] for p in listing["providers"] if p["id"] != "builtin"))

    # -- request/response adapters (pure) --------------------------------
    creds = {"api_key": "k", "secret_key": "s", "secret_id": "sid"}
    for pid in PROVIDER_ORDER:
        spec = PROVIDERS[pid]
        method, url, headers, body = build_request(
            spec,
            {"prompt": "anime girl, smile", "negative": "bad hands",
             "model": spec["default_model"], "size": spec["default_size"], "seed": 1},
            creds,
            access_token="tok" if pid == "qianfan" else None,
        )
        check(f"{pid} builds POST", method == "POST" and url.startswith("http") and body)
        check(f"{pid} has auth",
              "Authorization" in headers or "X-TC-Action" in headers
              or "X-App-Id" in headers or "access_token" in url)
    _, _, _, vbody = build_request(PROVIDERS["volcengine"], {"prompt": "x", "model": "m", "size": "1024x1024"}, {"api_key": "k"})
    check("volcengine disables watermark", b'"watermark": false' in vbody)
    check("dashscope size uses *",
          b'1024*1024' in build_request(PROVIDERS["dashscope"], {"prompt": "x", "model": "m", "size": "1024x1024"}, {"api_key": "k"})[3])
    check("hunyuan size uses :",
          '1024:1024' in build_request(PROVIDERS["hunyuan"], {"prompt": "x", "model": "m", "size": "1024x1024"}, creds)[3].decode("utf-8"))
    check("parse openai-style", parse_image({"data": [{"url": "http://a/b.png"}]}, PROVIDERS["zhipu"]) == "http://a/b.png")
    check("parse dashscope async", parse_image({"output": {"results": [{"url": "http://c/d.png"}]}}, PROVIDERS["dashscope"]) == "http://c/d.png")
    check("parse hunyuan base64", parse_image({"Response": {"ResultImage": "QUJD"}}, PROVIDERS["hunyuan"]) == "QUJD")

    # -- built-in generation (default core) ------------------------------
    builtin = await generate("a cute anime mascot", provider_id="builtin", size="512x512")
    check("builtin generate returns png", builtin.data[:8] == PNG_MAGIC and builtin.source == "builtin")
    check("builtin model label", builtin.model == "artgen-2d", builtin.model)

    # -- missing-credential guard (no network) ---------------------------
    store.save_credentials("zhipu", {"api_key": None})
    try:
        await generate("x", provider_id="zhipu")
        check("missing credential raises", False, "no error")
    except Exception as error:  # ProviderError
        check("missing credential raises", "缺少凭证" in str(error) or "api_key" in str(error), str(error))

    # -- custom provider CRUD --------------------------------------------
    created = store.add_custom({
        "label": "My Local SD",
        "endpoint": "http://127.0.0.1:9999/sdapi/v1/txt2img",
        "models": ["sd_xl_base"],
        "default_model": "sd_xl_base",
        "body": {"prompt": "{prompt}", "width": "{width}", "height": "{height}"},
        "image_paths": ["images.0"],
        "notes": "custom test",
    })
    cid = created["id"]
    check("custom provider created", store.get_spec(cid) is not None and store.is_custom(cid))
    store.update_custom(cid, {"label": "My Local SD v2"})
    check("custom provider updated", store.get_spec(cid)["label"] == "My Local SD v2")
    _, curl, _, _ = build_request(store.get_spec(cid), {"prompt": "p", "size": "1024x1024", "model": "sd_xl_base"}, {})
    check("custom endpoint used", curl.startswith("http://127.0.0.1:9999"))
    check("custom provider deleted", store.delete_custom(cid) and store.get_spec(cid) is None)

    # -- HTTP API + end-to-end asset creation ----------------------------
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        api = await client.get("/api/v1/providers")
        check("GET /providers 200", api.status_code == 200 and len(api.json()["providers"]) >= 8)

        # default path (no provider) -> builtin core, model name recorded
        created_asset = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "create a pixel fire mage mascot", "user_id": "prov"},
        )
        body = created_asset.json()
        gen = (body.get("result") or {}).get("generate_asset") or {}
        check("default uses builtin core", gen.get("image_source") == "builtin")
        check("default model name recorded", gen.get("image_model") == "artgen-2d", str(gen))
        asset_id = body.get("asset_id")
        detail = (await client.get(f"/api/v1/assets/{asset_id}")).json()
        meta_content = (detail.get("metadata_json") or {}).get("content", {})
        check("asset carries model metadata", meta_content.get("image_model") == "artgen-2d", str(meta_content.get("image_model")))
        check("asset carries provider metadata", meta_content.get("image_provider") == "builtin")

        # selecting a provider without credentials -> graceful fallback
        save = await client.put("/api/v1/providers/settings",
                                json={"provider": "volcengine", "model": "doubao-seedream-3-0-t2i-250415"})
        check("settings selection saved", save.status_code == 200 and save.json()["selected"]["provider"] == "volcengine")
        store.save_credentials("volcengine", {"api_key": None})

        fallback_asset = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "anime girl with silver hair", "user_id": "prov",
                  "provider": "volcengine"},
        )
        fgen = (fallback_asset.json().get("result") or {}).get("generate_asset") or {}
        check("missing api key degrades to builtin", fgen.get("image_source") == "builtin-fallback", str(fgen))
        check("failed provider still names model", fgen.get("image_provider") == "volcengine")

        # test endpoint reports failure without key (no network)
        tested = await client.post("/api/v1/providers/test", json={"provider": "volcengine"})
        check("provider test reports missing key", tested.status_code == 200 and tested.json()["ok"] is False)

        # mask: key never returned
        store.save_credentials("volcengine", {"api_key": "sk-1234567890abcdef"})
        masked = (await client.get("/api/v1/providers")).json()
        volc = next(p for p in masked["providers"] if p["id"] == "volcengine")
        check("key never exposed, only hint", "api_key" not in volc and volc["has_key"] and "****" in volc["key_hint"])
        store.save_credentials("volcengine", {"api_key": None})
        store.set_selected("builtin", "")

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
