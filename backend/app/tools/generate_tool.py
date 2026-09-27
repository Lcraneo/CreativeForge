"""Generate Tool (Phase 11.9 -> 12.9 -> 14.11 -> multi-provider).

Create mode:  prompt -> Windup adapter -> CreativeAsset.
Modify mode:  the character identity comes from the found DNA; only the
              changed part is regenerated on a new version image, keeping
              colour / face / proportions / style untouched.

Image backend (multi-model extension): the request may select a hosted image
provider (``context["request"]["provider"]`` + optional ``model``). When no
provider is selected — the default — the project's built-in generator is used,
so behaviour is unchanged for users who never configure an API. A failing
external provider degrades gracefully back to the built-in core.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.adapters.registry import ensure_adapters
from app.engines.character_dna.service import next_image_for
from app.engines.imagegen.providers import BUILTIN_PROVIDER, ProviderError
from app.engines.imagegen.service import generate as generate_image
from app.engines.imagegen.store import DATA_DIR
from app.tools.base import BaseTool

GENERATED_DIR = os.path.join(DATA_DIR, "generated")
BUILTIN_MODEL = "artgen-2d"


def _persist_bytes(data: bytes, mime: str) -> str:
    os.makedirs(GENERATED_DIR, exist_ok=True)
    extension = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
    filename = f"{uuid.uuid4().hex[:12]}{extension}"
    with open(os.path.join(GENERATED_DIR, filename), "wb") as handle:
        handle.write(data)
    return os.path.join("generated", filename)


class GenerateTool(BaseTool):
    name = "generate_asset"

    async def run(self, params: dict[str, Any]) -> dict[str, Any]:
        context = params
        services = context["services"]
        goal = context["goal"]
        base = context.get("character")
        request = context.get("request") or {}
        provider = (request.get("provider") or BUILTIN_PROVIDER) or BUILTIN_PROVIDER
        model = request.get("model")

        if base:
            # Phase 14 Step 4: identity-preserving modification.
            version = services.dna.versions.next_version(base["character_id"])
            image = next_image_for(base.get("image_stem") or base["character_id"], version)
            identity = dict(base.get("identity") or {})
            asset = {
                "identity": {
                    **identity,
                    "prompt": goal,
                    "character_id": base["character_id"],
                },
                "source": {
                    "provider": "windup",
                    "mode": "identity_preserved",
                    "base_character": base["character_id"],
                },
                "content": {"image": image},
                "style": {"name": identity.get("style") or "anime"},
                "version": {
                    "created": datetime.now(timezone.utc).isoformat(),
                    "label": version,
                },
            }
            context["version"] = version
        else:
            adapter = ensure_adapters().get("windup")
            asset = await adapter.generate({"prompt": goal})
            asset.setdefault("identity", {})["prompt"] = goal

        content = asset.setdefault("content", {})
        summary: dict[str, Any] = {
            "image": content.get("image"),
            "style": (asset.get("style") or {}).get("name"),
        }

        # -- image backend selection ------------------------------------
        if provider and provider != BUILTIN_PROVIDER:
            try:
                result = await generate_image(prompt=goal, provider_id=provider, model=model)
                relative = _persist_bytes(result.data, result.mime)
                content["image_render"] = relative
                content["image_render_mime"] = result.mime
                content["image_provider"] = result.provider
                content["image_provider_label"] = result.provider_label
                content["image_model"] = result.model
                content["image_source"] = "api"
                summary.update(
                    image_provider=result.provider,
                    image_provider_label=result.provider_label,
                    image_model=result.model,
                    image_source="api",
                    elapsed_ms=result.elapsed_ms,
                )
            except ProviderError as error:
                content["image_provider"] = provider
                content["image_model"] = model or ""
                content["image_source"] = "builtin-fallback"
                content["image_error"] = str(error)[:300]
                summary.update(
                    image_provider=provider,
                    image_model=model or "",
                    image_source="builtin-fallback",
                    image_error=str(error)[:300],
                )
        else:
            content["image_provider"] = BUILTIN_PROVIDER
            content["image_provider_label"] = "项目内置管线"
            content["image_model"] = BUILTIN_MODEL
            content["image_source"] = "builtin"
            summary.update(
                image_provider=BUILTIN_PROVIDER,
                image_provider_label="项目内置管线",
                image_model=BUILTIN_MODEL,
                image_source="builtin",
            )

        context["asset"] = asset
        return summary
