"""Windup mapper (Phase 12.6): provider payload -> CreativeAsset."""

from datetime import datetime, timezone

from app.utils import slugify


def map_to_asset(data: dict) -> dict:
    """Map `{"image_url", "style", ...}` onto the CreativeAsset contract."""
    name = slugify(str(data.get("name") or "generated_character"))
    return {
        "identity": {
            "name": name,
        },
        "source": {
            "provider": "windup",
            "raw": {k: v for k, v in data.items() if k != "image_url"},
        },
        "content": {
            "image": data["image_url"],
        },
        "style": {
            "name": data.get("style") or "unknown",
        },
        "version": {
            "created": datetime.now(timezone.utc).isoformat(),
        },
    }
