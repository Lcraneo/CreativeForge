"""角色资产包一键导出：一个角色 = 原画 + 三视图 + 全动作 GIF + 引擎包。

包结构（``<asset>_package_<ts>.zip``）::

    README.md                人类可读清单
    manifest.json            机器可读清单（creativeforge-character-package/1）
    artwork/front|side|back.png   三视图（design_views，缺失视图自动跳过）
    artwork/source_ai.png    AI 原画
    artwork/cutout.png       透明底立绘（如有）
    artwork/restyle.png      风格迁移版（如有）
    animations/<action>__<engine>.gif      每个动作的成品动画（每动作取最新）
    animations/<action>__<engine>_sheet.png
    engine/...               GImport 一键导出工程包（Character/Animation/
                             Prefab/Config/Texture 全套，复用 ExportService）

全部素材取自本地落盘产物；缺失项跳过并在 manifest 缺失清单里注明，
任何单项失败都不阻塞整包导出。
"""

import json
import os
import time
import zipfile

# 与 studio/backend/api/routes.py 的 ANIMATION_DIR 同源（避免循环 import，
# 由文件位置推导：studio/backend/data/animation）
_ANIMATION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "animation",
)


def _read_generated(file_name):
    """按 generated 目录解析产物文件字节（路径穿越防护内建）。"""

    from studio.backend.model_service.service import safe_generated_path

    path = safe_generated_path(os.path.basename(str(file_name or "")))
    if not path:
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _read_animation(file_name):
    path = os.path.join(_ANIMATION_DIR, os.path.basename(str(file_name or "")))
    if not file_name or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def export_character_package(asset, animations, output_dir, engine="cocos"):
    """组装并落盘角色资产包。

    ``asset``：资产 dict；``animations``：该资产关联的动画 meta 列表
    （``AnimationService.animations_for_asset`` 的输出，新→旧）。
    返回结果 dict（含 ``path``，路由层可 pop 掉再回给前端）。"""

    from gimport.exporter.one_click_export import OneClickExporter

    from studio.backend.export_service.service import ExportService

    asset_id = asset.get("id", "asset")
    os.makedirs(output_dir, exist_ok=True)

    # ── 引擎工程包条目（复用一键导出的全部 JSON + Texture 渲染）──────────
    engine_entries = []
    validation = None
    engine_error = None
    try:
        export = OneClickExporter().export(asset, engine)
        result = export["result"]
        validation = result.get("validation")
        for name, payload in ExportService._entries(asset_id, asset, result):
            engine_entries.append(("engine/" + name, payload))
    except Exception as error:  # noqa: BLE001 - 引擎包失败不拖垮美术素材
        engine_error = str(error)[:140]

    # ── 美术素材 ──────────────────────────────────────────────────────────
    artwork_entries: list[tuple[str, bytes]] = []
    artwork_manifest: dict[str, str] = {}
    missing: list[str] = []

    def _add_artwork(file_name, arcname, key):
        data = _read_generated(file_name)
        if data is None:
            missing.append(key)
            return
        artwork_entries.append(("artwork/" + arcname, data))
        artwork_manifest[key] = arcname

    views = asset.get("design_views") or {}
    for view in ("front", "side", "back"):
        meta = views.get(view)
        _add_artwork(
            meta.get("file") if isinstance(meta, dict) else None,
            view + ".png",
            "view_" + view,
        )

    image = asset.get("image")
    if isinstance(image, dict):
        _add_artwork(image.get("file"), "source_ai.png", "source_ai")
    if asset.get("cutout_png"):
        _add_artwork(asset["cutout_png"], "cutout.png", "cutout")
    restyle = asset.get("restyle")
    if isinstance(restyle, dict):
        _add_artwork(restyle.get("file"), "restyle.png", "restyle")

    # ── 动画：每个动作取最新一条，GIF + 拍板图成对打包 ────────────────────
    animation_entries: list[tuple[str, bytes]] = []
    animation_manifest: list[dict] = []
    chosen: dict[str, tuple] = {}
    for meta in animations:
        action = meta.get("requested_action") or meta.get("action") or "action"
        source = meta.get("source") or "unknown"
        engine_tag = {"video": "ai-video", "skeletal": "skeletal", "sequence": "sequence"}.get(
            source, source
        )
        stamp = meta.get("created_at", 0)
        prev = chosen.get(action)
        if prev is None or stamp > prev[0]:
            chosen[action] = (stamp, meta, engine_tag)
    for action, (stamp, meta, engine_tag) in sorted(chosen.items()):
        urls = meta.get("urls") or {}
        gif_data = _read_animation(urls.get("gif"))
        if gif_data is None:
            missing.append("animation:" + action)
            continue
        animation_entries.append(
            ("animations/{}__{}.gif".format(action, engine_tag), gif_data)
        )
        sheet_data = _read_animation(urls.get("sheet"))
        if sheet_data is not None:
            animation_entries.append(
                ("animations/{}__{}_sheet.png".format(action, engine_tag), sheet_data)
            )
        animation_manifest.append(
            {
                "action": action,
                "engine": engine_tag,
                "frames": meta.get("frames") or len(meta.get("frame_urls") or []),
                "fps": meta.get("fps"),
                "gif": "{}__{}.gif".format(action, engine_tag),
                "animation_id": meta.get("id"),
                "generated_at": stamp,
            }
        )

    # ── 清单 ──────────────────────────────────────────────────────────────
    manifest = {
        "format": "creativeforge-character-package/1",
        "asset": {
            "id": asset_id,
            "name": asset.get("name"),
            "type": asset.get("type", "character"),
            "role": asset.get("role"),
            "engine": engine,
        },
        "generated_at": time.time(),
        "artwork": artwork_manifest,
        "animations": animation_manifest,
        "engine_package": "engine/" if engine_entries else None,
        "engine_error": engine_error,
        "engine_validation": validation,
        "missing": missing,
        "counts": {
            "artwork": len(artwork_entries),
            "animations": len(animation_entries),
            "engine_files": len(engine_entries),
        },
    }
    readme = (
        "# {name} — CreativeForge 角色资产包\n\n"
        "asset: {aid} · engine: {engine}\n"
        "三视图: {views} · 动作动画: {actions} · 引擎文件: {efiles}\n\n"
        "## 目录\n"
        "- `artwork/` 原画、三视图、透明底、风格迁移版\n"
        "- `animations/` 每个动作的成品 GIF + 拍板图（`<动作>__<引擎>.gif`）\n"
        "- `engine/` GImport 一键导出的引擎工程包（可直接导入 {engine}）\n"
        "- `manifest.json` 完整清单与缺失项\n"
    ).format(
        name=asset.get("name") or asset_id,
        aid=asset_id,
        engine=engine,
        views=len([k for k in artwork_manifest if k.startswith("view_")]),
        actions=len(animation_manifest),
        efiles=len(engine_entries),
    )

    package_name = "{}_package_{}.zip".format(asset_id, int(time.time() * 1000))
    package_path = os.path.join(output_dir, package_name)
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("README.md", readme)
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, payload in artwork_entries + animation_entries + engine_entries:
            bundle.writestr(name, payload)

    return {
        "package": package_name,
        "asset_id": asset_id,
        "engine": engine,
        "artwork_count": manifest["counts"]["artwork"],
        "animations": animation_manifest,
        "engine_files": len(engine_entries),
        "engine_error": engine_error,
        "missing": missing,
        "files": ["README.md", "manifest.json"]
        + [name for name, _ in artwork_entries + animation_entries + engine_entries],
        "size_bytes": os.path.getsize(package_path),
        "download_url": "/api/exports/" + package_name,
        "path": package_path,
    }
