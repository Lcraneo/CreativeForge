"""Export packaging (Phase 21): engine resource tree -> real zip download.

The MVP demo output (spec 二):

    RobotCat/
    ├── DNA.json                                 character DNA record
    ├── skill.json                               combat skill blueprint
    └── assets/characters/<name>/
        ├── textures/<name>_atlas.png
        ├── spriteframes/<name>.plist
        ├── animations/<clip>.anim
        └── prefab/<Name>.prefab                 (+ collider payloads)

Texture entries are exporter metadata today; the packager renders a valid
placeholder PNG (pure stdlib) so the archive is openable end to end — swap
in the real atlas bytes when the pixel engine writes them.
"""

import io
import json
import struct
import zipfile
import zlib
from typing import Any
from urllib.parse import quote

from app.core.config import settings
from app.engines.gimport.exporter.registry import register_default_exporters
from app.engines.gimport.pipeline.processor import GImportProcessor
from app.utils import slugify

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_MAX_DIM = 512


async def run_export(row, engine: str | None = None) -> tuple[dict[str, Any], str]:
    """Run GImport for the target engine and persist the resource tree on
    the asset row (shared by POST /export, export.zip and MCP invoke)."""
    asset = dict(row.metadata_json or {})
    engine_target = (
        engine
        or (asset.get("engine") or {}).get("target")
        or settings.ENGINE_TARGET
    )
    register_default_exporters()
    processor = GImportProcessor(default_target=engine_target)
    asset["engine"] = {"target": engine_target}
    exported = await processor.process(asset)
    row.metadata_json = exported
    return exported, engine_target


def placeholder_png(size: Any, rgba: tuple[int, int, int, int] = (36, 41, 54, 255)) -> bytes:
    """Minimal valid RGBA PNG of the atlas size, no external deps."""
    dims = size if isinstance(size, (list, tuple)) else (size or {}).get("size") or [128, 128]
    width = max(1, min(int(dims[0] or 128), PNG_MAX_DIM))
    height = max(1, min(int(dims[1] or 128), PNG_MAX_DIM))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = (b"\x00" + bytes(rgba) * width) * height
    return (
        PNG_MAGIC
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _serialize(path: str, content: Any) -> bytes:
    if path.lower().endswith(".png") and isinstance(content, dict):
        return placeholder_png(content)
    if isinstance(content, str):
        return content.encode("utf-8")
    return json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")


def package_export_zip(asset: dict[str, Any], engine: str) -> tuple[bytes, str]:
    """Engine resource tree + DNA/skill blueprints -> (zip bytes, filename)."""
    resources = (asset.get("engine") or {}).get("resources") or {}
    name = (asset.get("identity") or {}).get("name") or "character"
    root = resources.get("root") or f"assets/characters/{name}"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if asset.get("dna"):
            archive.writestr(
                "DNA.json", json.dumps(asset["dna"], ensure_ascii=False, indent=2)
            )
        combat = asset.get("combat") or {}
        skills = combat.get("skills") or []
        if skills:
            archive.writestr(
                "skill.json", json.dumps(skills[0], ensure_ascii=False, indent=2)
            )
        hitboxes = combat.get("hitboxes") or []
        hurtboxes = combat.get("hurtboxes") or []
        if hitboxes or hurtboxes:
            archive.writestr(
                "collider.json",
                json.dumps(
                    {"hitboxes": hitboxes, "hurtboxes": hurtboxes},
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        for path, content in sorted((resources.get("files") or {}).items()):
            archive.writestr(f"{root}/{path}", _serialize(path, content))
    return buffer.getvalue(), f"{slugify(name)}_{engine}_export.zip"


def content_disposition(filename: str) -> str:
    return f"attachment; filename=export.zip; filename*=UTF-8''{quote(filename)}"
