"""Real game-asset package export: GImport result -> downloadable zip."""

import json
import os
import zipfile

from gimport.exporter.one_click_export import OneClickExporter

EXPORT_CONTENTS = ["Character", "Animation", "Prefab", "Config"]


class ExportService:
    """Turns a CreativeAsset into a real zip package on disk.

    Contents follow the one-click export layout:
        Character/<asset>.manifest.json
        Animation/<asset>.anim.json
        Prefab/<asset>.prefab.json
        Config/atlas.json / controller.json / validation.json / README.md
    """

    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def export(self, asset, engine="cocos"):
        export = OneClickExporter().export(asset, engine)
        result = export["result"]
        asset_id = asset.get("id", "asset")

        package_name = export["package"]
        package_path = os.path.join(self.output_dir, package_name)
        entries = self._entries(asset_id, asset, result)
        with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, text in entries:
                bundle.writestr(name, text)

        return {
            "package": package_name,
            "engine": engine,
            "asset_id": asset_id,
            "contents": EXPORT_CONTENTS,
            "files": [name for name, _ in entries],
            "path": package_path,
            "size_bytes": os.path.getsize(package_path),
            "download_url": "/api/exports/{}".format(package_name),
            "validation": result["validation"],
        }

    def export_batch(self, assets, engine="cocos"):
        """P1-B 批量导出：多个资产合并为一个 zip，包内按 <asset_id>/ 分目录，
        并附带整批 validation 汇总与 README 清单。"""

        import time

        all_entries = []
        summary = []
        for asset in assets:
            asset_id = asset.get("id", "asset")
            try:
                export = OneClickExporter().export(asset, engine)
                result = export["result"]
            except Exception as error:  # noqa: BLE001 - skip broken asset, keep batch
                summary.append(
                    {
                        "asset_id": asset_id,
                        "name": asset.get("name"),
                        "ok": False,
                        "error": str(error)[:120],
                    }
                )
                continue
            for name, text in self._entries(asset_id, asset, result):
                all_entries.append(("{}/{}".format(asset_id, name), text))
            summary.append(
                {
                    "asset_id": asset_id,
                    "name": asset.get("name"),
                    "ok": True,
                    "validation_score": (result.get("validation") or {}).get("score"),
                }
            )

        readme = (
            "# CreativeForge Batch Export\n\n"
            "engine: {engine}\nassets: {count}\nexported_at: {at:.0f}\n\n"
            "| asset | name | ok | validation |\n| --- | --- | --- | --- |\n{rows}\n"
        ).format(
            engine=engine,
            count=len(summary),
            at=time.time(),
            rows="\n".join(
                "| {asset_id} | {name} | {ok} | {score} |".format(
                    asset_id=item.get("asset_id"),
                    name=item.get("name") or "—",
                    ok="yes" if item.get("ok") else "NO",
                    score=(
                        item.get("validation_score")
                        if item.get("validation_score") is not None
                        else "—"
                    ),
                )
                for item in summary
            ),
        )
        all_entries.append(("README.md", readme))

        package_name = "batch_{}_{}.zip".format(engine, int(time.time() * 1000))
        package_path = os.path.join(self.output_dir, package_name)
        with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, text in all_entries:
                bundle.writestr(name, text)

        return {
            "package": package_name,
            "engine": engine,
            "assets": summary,
            "count": sum(1 for item in summary if item.get("ok")),
            "files": [name for name, _ in all_entries],
            "size_bytes": os.path.getsize(package_path),
            "download_url": "/api/exports/{}".format(package_name),
        }

    @staticmethod
    def _entries(asset_id, asset, result):
        manifest = result["manifest"]
        animation = result["animation"]
        clip = animation.get("clip", animation.get("animation", {}))
        prefab = result["prefab"]["prefab"]
        atlas = result["atlas"]["atlas"]
        controller = {
            "name": "{}.controller".format(asset_id),
            "parameters": ["speed", "isAttacking"],
            "layers": ["Base Layer"],
            "clips": [clip.get("name", asset_id)],
        }
        readme = (
            "# {name} — CreativeForge Game Asset\n\n"
            "asset id: {aid}\ntype: {type}\nengine: ready\n"
            "\n## Texture/\n"
            "- `<asset>_front.png` — 正面立绘（512px，可直接做 Sprite）\n"
            "- `<asset>_sheet.png` — 三视图参考（正/侧/背）\n"
            "- `<asset>_edited.png` — 像素工作台编辑版（如做过编辑）\n"
            "- `<asset>_source.png` — AI 原画（如存在）\n\n"
            "generated by CreativeForge GImport (one-click export)\n"
        ).format(
            name=asset.get("name", asset_id), aid=asset_id, type=asset.get("type", "character")
        )

        entries = [
            (
                "Character/{}.manifest.json".format(asset_id),
                json.dumps(manifest, ensure_ascii=False, indent=2),
            ),
            (
                "Animation/{}.anim.json".format(asset_id),
                json.dumps(clip, ensure_ascii=False, indent=2),
            ),
            (
                "Prefab/{}.prefab.json".format(asset_id),
                json.dumps(prefab, ensure_ascii=False, indent=2),
            ),
            ("Config/atlas.json", json.dumps(atlas, ensure_ascii=False, indent=2)),
            ("Config/controller.json", json.dumps(controller, ensure_ascii=False, indent=2)),
            (
                "Config/validation.json",
                json.dumps(result["validation"], ensure_ascii=False, indent=2),
            ),
            ("README.md", readme),
        ]

        # ── P0：把美术资源真正打进包里（此前 zip 只有 JSON 清单）──────────
        for name, png in ExportService._texture_entries(asset_id, asset):
            entries.append((name, png))
        return entries

    @staticmethod
    def _texture_entries(asset_id, asset):
        """Render the asset's artwork into the package (best-effort: a render
        failure never blocks the JSON export)."""

        from io import BytesIO

        from PIL import Image

        from artgen import render_asset_sheet, render_asset_view

        def png_bytes(image):
            buffer = BytesIO()
            image.save(buffer, "PNG")
            return buffer.getvalue()

        produced = []
        try:
            produced.append(
                (
                    "Texture/{}_front.png".format(asset_id),
                    png_bytes(Image.open(BytesIO(render_asset_view(asset, "front", 512)))),
                )
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            produced.append(
                (
                    "Texture/{}_sheet.png".format(asset_id),
                    png_bytes(Image.open(BytesIO(render_asset_sheet(asset, 512, 24)))),
                )
            )
        except Exception:  # noqa: BLE001
            pass

        # 像素工作台编辑版渲染图
        edited = (asset.get("pixel") or {}).get("edited_png") or ""
        if edited:
            from studio.backend.model_service.service import safe_generated_path

            path = safe_generated_path(os.path.basename(edited))
            if path:
                with open(path, "rb") as handle:
                    produced.append(("Texture/{}_edited.png".format(asset_id), handle.read()))

        # AI 原画
        image = asset.get("image") or {}
        source = asset.get("source") or {}
        candidates = []
        for meta in (image, source.get("ai_image")):
            if isinstance(meta, dict) and meta.get("file"):
                candidates.append(os.path.basename(str(meta["file"])))
        for name in candidates:
            from studio.backend.model_service.service import safe_generated_path

            path = safe_generated_path(name)
            if path:
                with open(path, "rb") as handle:
                    produced.append(("Texture/{}_source.png".format(asset_id), handle.read()))
                break
        return produced
