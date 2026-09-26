"""Holonic adapter stub (Phase 12.2).

Holonic is the video / task oriented external capability. Only the adapter
boundary is frozen here; the real client lands with the Holonic integration.
"""

from datetime import datetime, timezone
from typing import Any

from app.adapters.base import AssetAdapter
from app.utils import slugify


class HolonicAdapter(AssetAdapter):
    name = "holonic"

    async def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        return await self.convert(
            {
                "task": request.get("prompt", ""),
                "video_url": f"{slugify(request.get('prompt', 'holonic'))}.mp4",
            }
        )

    async def convert(self, raw_asset: dict[str, Any]) -> dict[str, Any]:
        return {
            "identity": {"name": slugify(str(raw_asset.get("task") or "holonic_task"))},
            "source": {"provider": "holonic", "raw": raw_asset},
            "content": {"video": raw_asset.get("video_url")},
            "style": {"name": "unknown"},
            "version": {"created": datetime.now(timezone.utc).isoformat()},
        }
