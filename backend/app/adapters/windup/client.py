"""Windup HTTP client (Phase 12.5) + deterministic offline stand-in."""

from typing import Any

import httpx

from app.utils import slugify, stable_hash


class WindupClient:
    """Real client: owns all external communication with Windup."""

    def __init__(self, api_key: str, base_url: str, timeout: float = 60.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, prompt: str, style: str | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url + "/generate",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"prompt": prompt, "style": style},
            )
            response.raise_for_status()
            return response.json()


class MockWindupClient:
    """Offline stand-in used while WINDUP_BASE_URL is unset (Phase 11 mock).

    Returns the Phase 11 shape (`image_url` + `style`) deterministically so
    the pipeline is runnable end to end without credentials.
    """

    async def generate(self, prompt: str, style: str | None = None) -> dict[str, Any]:
        return {
            "image_url": f"{slugify(prompt)}.png",
            "style": style or "anime",
            "seed": stable_hash(prompt) % 100000,
        }
