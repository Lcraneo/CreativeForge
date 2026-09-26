"""Character image verification (Phase 21 image fix), no pytest dependency.

Covers the reported defect: character artwork never reached any product
surface. This checks the full serving path end to end —

    * GET /assets/{id}/image.png returns image/png with valid PNG structure
    * format / colour-type / bit-depth / dimension compliance at several sizes
    * size clamping + unknown-asset 404 (frontend fallback trigger)
    * deterministic bytes for the same asset, distinct across assets
    * content.image_url is stamped on the persisted asset
    * export.zip textures carry the real character art (not a flat block)
    * artgen palette resolution (role dict + flat hex list + empty)

Run: python backend/tests/run_image_tests.py
"""

import asyncio
import io
import os
import struct
import sys
import tempfile
import zipfile
import zlib

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_image_test.db")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"

import httpx  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

CHECKS = []


def check(name: str, condition: bool, detail: str = ""):
    CHECKS.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not condition else ""))


def png_info(data: bytes):
    """(width, height, bit_depth, color_type, raw_scanlines) for our PNGs."""
    assert data[:8] == PNG_MAGIC, "not a png"
    width, height = struct.unpack(">II", data[16:24])
    bit_depth, color_type = data[24], data[25]
    i, idat = 8, b""
    while i < len(data):
        length = struct.unpack(">I", data[i:i + 4])[0]
        tag = data[i + 4:i + 8]
        if tag == b"IDAT":
            idat += data[i + 8:i + 8 + length]
        i += 12 + length
    return width, height, bit_depth, color_type, zlib.decompress(idat)


def distinct_pixels(width: int, height: int, raw: bytes) -> int:
    stride = width * 4
    seen = set()
    for y in range(height):
        base = y * (stride + 1) + 1
        row = raw[base:base + stride]
        for x in range(0, stride, 4):
            seen.add(bytes(row[x:x + 4]))
    return len(seen)


async def main() -> int:
    from app.core.database import init_models
    from app.main import app

    await init_models()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        goal = "create a pixel fire mage boss with attack skill, import unity"
        created = await client.post(
            "/api/v1/assets/create", json={"prompt": goal, "user_id": "img"}
        )
        asset_id = created.json().get("asset_id")
        check("asset created", bool(asset_id), str(created.status_code))

        # -- format / dimension compliance at the product sizes --------------
        for size in (64, 128, 256, 512):
            response = await client.get(
                f"/api/v1/assets/{asset_id}/image.png", params={"size": size}
            )
            check(
                f"size={size} returns image/png",
                response.status_code == 200
                and response.headers.get("content-type") == "image/png",
                f"{response.status_code} {response.headers.get('content-type')}",
            )
            width, height, depth, color, raw = png_info(response.content)
            check(
                f"size={size} is {size}x{size}",
                width == size and height == size,
                f"{width}x{height}",
            )
            check(
                f"size={size} 8-bit RGBA non-interlaced",
                depth == 8 and color == 6,
                f"depth={depth} color={color}",
            )
            check(
                f"size={size} renders real artwork",
                distinct_pixels(width, height, raw) > 1,
                str(distinct_pixels(width, height, raw)),
            )

        # -- three orthographic views (2D): front / left-side / back ---------
        for view in ("front", "side", "back"):
            response = await client.get(
                f"/api/v1/assets/{asset_id}/image.png",
                params={"view": view, "size": 256},
            )
            check(
                f"view={view} returns 2D png",
                response.status_code == 200
                and response.headers.get("content-type") == "image/png"
                and response.headers.get("x-image-style") == "2d",
                f"{response.status_code} {dict(response.headers)}",
            )
            width, height, depth, color, raw = png_info(response.content)
            check(f"view={view} 256x256 RGBA", width == 256 and height == 256 and depth == 8 and color == 6)
            check(f"view={view} renders artwork", distinct_pixels(width, height, raw) > 1)

        check(
            "views differ from each other",
            (await client.get(f"/api/v1/assets/{asset_id}/image.png", params={"view": "front"})).content
            != (await client.get(f"/api/v1/assets/{asset_id}/image.png", params={"view": "side"})).content,
        )

        sheet = await client.get(
            f"/api/v1/assets/{asset_id}/views.png", params={"size": 192, "gap": 16}
        )
        sw, sh, sdepth, scolor, sraw = png_info(sheet.content)
        check("sheet is image/png 2d", sheet.status_code == 200 and sheet.headers.get("x-image-style") == "2d")
        check("sheet width = 3 views + gaps", sw == 192 * 3 + 16 * 2 and sh == 192, f"{sw}x{sh}")
        check("sheet is non-empty art", distinct_pixels(sw, sh, sraw) > 1)

        # -- size clamping ---------------------------------------------------
        low = await client.get(
            f"/api/v1/assets/{asset_id}/image.png", params={"size": 1}
        )
        low_w, _, _, _, _ = png_info(low.content)
        check("size clamped up to >=32", low_w >= 32, str(low_w))

        high = await client.get(
            f"/api/v1/assets/{asset_id}/image.png", params={"size": 99999}
        )
        high_w, _, _, _, _ = png_info(high.content)
        check("size clamped down to <=1024", high_w <= 1024, str(high_w))

        # -- determinism + caching headers ----------------------------------
        first = await client.get(f"/api/v1/assets/{asset_id}/image.png")
        second = await client.get(f"/api/v1/assets/{asset_id}/image.png")
        check("deterministic bytes", first.content == second.content)
        check(
            "cache header present",
            "max-age" in first.headers.get("cache-control", ""),
            first.headers.get("cache-control", ""),
        )

        # -- asset carries a loadable reference ------------------------------
        detail = (await client.get(f"/api/v1/assets/{asset_id}")).json()
        content = (detail.get("metadata_json") or {}).get("content", {})
        ref = content.get("image_url")
        check(
            "content.image_url points at the image endpoint",
            isinstance(ref, str) and ref.startswith(f"/api/v1/assets/{asset_id}/image.png"),
            str(ref),
        )
        check(
            "content carries three view urls + 2d style",
            content.get("image_style") == "2d"
            and set((content.get("views") or {}).keys()) == {"front", "side", "back"},
            str(content.get("views")),
        )

        # -- export archive carries the real image ---------------------------
        zipped = await client.get(
            f"/api/v1/assets/{asset_id}/export.zip", params={"engine": "cocos"}
        )
        archive = zipfile.ZipFile(io.BytesIO(zipped.content))
        textures = [
            name
            for name in archive.namelist()
            if "/textures/" in name and name.lower().endswith(".png")
        ]
        check("export zip has a texture", bool(textures), str(archive.namelist()))
        if textures:
            tw, th, tdepth, tcolor, traw = png_info(archive.read(textures[0]))
            check(
                "zip texture is valid png",
                tdepth == 8 and tcolor == 6,
                f"depth={tdepth} color={tcolor}",
            )
            check(
                "zip texture shows character art (not flat)",
                distinct_pixels(tw, th, traw) > 1,
                str(distinct_pixels(tw, th, traw)),
            )
        check(
            "export zip has a three-view sheet",
            any(name.endswith("_views.png") for name in archive.namelist()),
            str(archive.namelist()),
        )

        # -- unknown asset -> 404 (drives the frontend fallback) -------------
        missing = await client.get("/api/v1/assets/does-not-exist/image.png")
        check("unknown asset returns 404", missing.status_code == 404)

        # -- two different assets render differently -------------------------
        other = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "create a cyberpunk robot cat ninja, import cocos"},
        )
        other_id = other.json().get("asset_id")
        other_img = await client.get(f"/api/v1/assets/{other_id}/image.png")
        check("different assets differ", other_img.content != first.content)

    # -- artgen palette resolution ------------------------------------------
    from artgen import render_character_png, resolve_palette

    flat = resolve_palette(["#111111", "#3a3a3a", "#ffaa00", "#00c8ff", "#8a5a2a"])
    check(
        "flat palette mapped to semantic roles",
        {"outline", "base", "highlight", "accent", "hair"} <= set(flat),
    )
    check("flat palette outline is dark", flat["outline"] == "#111111", flat["outline"])

    role_bytes = render_character_png({"palette": {"hair": "#ff00ff"}, "seed": 3})
    check("role-dict palette renders valid png", role_bytes[:8] == PNG_MAGIC)
    check("empty palette falls back to defaults", render_character_png({})[:8] == PNG_MAGIC)
    check(
        "seed is deterministic",
        render_character_png({"seed": "abc"})
        == render_character_png({"seed": "abc"}),
    )

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
