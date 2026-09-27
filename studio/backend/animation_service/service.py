"""Animation service (Studio): source image -> style-consistent animation.

Bridges the workbench asset/upload to the shared ``artgen`` animation pipeline
(style analysis + character extraction + pose frames + consistency check +
GIF/sheet encoding) and persists the artefacts for the console to display.
"""

import base64
import json
import os
import time
import uuid
from typing import Any

from artgen import ACTIONS, STYLE_LABELS, create_animation
from artgen.character2d import asset_params
from artgen.gif import decode_image
from artgen.style import analyze_rgba, dominant_palette, extract_character


class AnimationService:
    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    # -- public API -----------------------------------------------------

    def create(
        self,
        asset: dict[str, Any] | None = None,
        image_bytes: bytes | None = None,
        action: str = "walk",
        fps: int = 12,
        duration: float = 1.0,
        size: int = 512,
        consistency_floor: float = 0.6,
        skeletal: bool = False,
    ) -> dict[str, Any]:
        action = action if action in ACTIONS else "walk"

        params = None
        source_bytes = None
        source_kind = "builtin"

        if skeletal:
            # 全身骨骼模式：姿态引擎驱动的关节动画（含预备/跟随/重叠动作），
            # 角色使用资产 CharacterSpec / 上传图调色板，比例全程恒定
            source_kind = "skeletal"
            if image_bytes:
                w, h, rgba = decode_image(image_bytes)
                params = {"palette": dominant_palette(w, h, rgba, count=8), "seed": f"upload-{action}"}
            elif asset is not None:
                params = asset_params(asset)
            else:
                params = {"palette": None, "seed": f"{action}-{fps}"}
        elif image_bytes:
            source_kind = "upload"
            source_bytes = image_bytes
        elif asset is not None:
            source_kind = "asset"
            params = asset_params(asset)
            source_bytes = self._asset_render(asset)
            if source_bytes is None:
                # 无 AI 原画/本地文件（如重启后的历史资产）：退回资产正面立绘
                # （与前端展示的 /api/assets/{id}/image.png 同一渲染），保证关键帧
                # 从资产图本身派生，而不是落到程序化像素小人
                try:
                    from artgen import render_asset_view

                    source_bytes = render_asset_view(
                        asset, "front", max(384, min(1024, int(size)))
                    )
                except Exception:
                    source_bytes = None

        result = create_animation(
            params=params,
            action=action,
            fps=fps,
            duration=duration,
            size=size,
            reference=source_bytes,
            source_bytes=source_bytes,
            consistency_floor=consistency_floor,
        )

        animation_id = uuid.uuid4().hex[:12]
        return self._persist(result, animation_id, source_kind)

    def create_sequence(
        self,
        frames: list[bytes],
        fps: int = 12,
        size: int = 384,
        consistency_floor: float = 0.6,
    ) -> dict[str, Any]:
        """Compose an animation from user-imported sequence frames (标准序列帧
        工作流): frames are fitted to a shared canvas and packed as-is into a
        looping GIF — no re-drawing, no pose synthesis, imported order kept."""
        from artgen import compose_animation

        result = compose_animation(
            frame_bytes=frames,
            fps=fps,
            size=size,
            consistency_floor=consistency_floor,
        )
        animation_id = uuid.uuid4().hex[:12]
        return self._persist(result, animation_id, "sequence")

    def _persist(self, result: dict[str, Any], animation_id: str, source_kind: str) -> dict[str, Any]:
        gif_name = f"{animation_id}.gif"
        sheet_name = f"{animation_id}_sheet.png"
        thumb_name = f"{animation_id}_thumb.png"
        self._write(gif_name, result["gif"])
        self._write(sheet_name, result["sheet"])
        self._write(thumb_name, result["frames"][0])
        # 每一帧单独落盘，交付完整的图像序列
        frame_urls = []
        for index, png in enumerate(result["frames"]):
            name = f"{animation_id}_f{index:02d}.png"
            self._write(name, png)
            frame_urls.append(f"/api/animation/{name}")

        meta = {
            "id": animation_id,
            "source": source_kind,
            "action": result["action"],
            "fps": result["fps"],
            "duration": result["duration"],
            "frame_count": result["frame_count"],
            "size": result["size"],
            "loop": result["loop"],
            "style": result["style"],
            "style_label": STYLE_LABELS.get(result["style"]["style"], result["style"]["style"]),
            "character": result["character"],
            "consistency": result["consistency"],
            "per_frame": result["per_frame"],
            "sheet_size": result["sheet_size"],
            "frames": len(result["frames"]),
            "frame_urls": frame_urls,
            "urls": {
                "gif": f"/api/animation/{gif_name}",
                "sheet": f"/api/animation/{sheet_name}",
                "thumb": f"/api/animation/{thumb_name}",
            },
            "created_at": time.time(),
        }
        self._write(f"{animation_id}.json", json.dumps(meta, ensure_ascii=False).encode("utf-8"))
        return meta

    # -- helpers --------------------------------------------------------

    def _asset_render(self, asset: dict[str, Any]):
        """Local source image bytes for the asset (generated dir / AI 原画), or None."""
        from studio.backend.model_service.service import GENERATED_DIR

        base = GENERATED_DIR
        candidates: list[str] = []
        metas = [asset.get("image")]
        source = asset.get("source")
        if isinstance(source, dict):
            metas.append(source.get("ai_image"))
        for meta in metas:
            if not isinstance(meta, dict):
                continue
            if meta.get("path"):
                candidates.append(str(meta["path"]))
            if meta.get("file"):
                candidates.append(os.path.join(base, os.path.basename(str(meta["file"]))))
            if meta.get("url"):
                candidates.append(str(meta["url"]))
        content = asset.get("content") or {}
        if isinstance(content, dict) and content.get("image_render"):
            candidates.append(os.path.join(base, os.path.basename(str(content["image_render"]))))

        remote = None
        for candidate in candidates:
            if candidate.startswith(("http://", "https://")):
                remote = remote or candidate
                continue
            # "/api/generated/<name>" 形式的本地 URL → generated 目录
            name = os.path.basename(candidate.split("?")[0])
            for path in (candidate, os.path.join(base, name)):
                if name and path and os.path.isfile(path):
                    with open(path, "rb") as handle:
                        return handle.read()
        if remote:
            # 远端 AI 原画仅存 URL：先按文件名找本地缓存，未命中再拉取
            name = os.path.basename(remote.split("?")[0])
            local = os.path.join(base, name)
            if name and os.path.isfile(local):
                with open(local, "rb") as handle:
                    return handle.read()
            try:
                import urllib.request

                with urllib.request.urlopen(remote, timeout=20) as response:
                    return response.read()
            except Exception:
                return None
        return None

    def _write(self, name: str, payload: bytes) -> None:
        with open(os.path.join(self.directory, name), "wb") as handle:
            handle.write(payload)

    def path(self, name: str) -> str | None:
        safe = os.path.basename(name)
        if safe != name:
            return None
        full = os.path.join(self.directory, safe)
        return full if os.path.isfile(full) else None


def analyze_only(image_bytes: bytes) -> dict[str, Any]:
    """Style + character report for an image without animating it."""
    width, height, rgba = decode_image(image_bytes)
    return {
        "style": analyze_rgba(width, height, rgba),
        "character": extract_character(width, height, rgba),
        "palette": dominant_palette(width, height, rgba, count=8),
    }
