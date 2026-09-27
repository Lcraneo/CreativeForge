"""Provider settings store (persisted JSON, credentials never returned).

Layout of ``backend/data/image_providers.json``::

    {
      "selected": {"provider": "builtin", "model": ""},
      "custom":  [ {provider spec} ],
      "credentials": {"volcengine": {"api_key": "..."}}
    }

Keys live only on disk (git-ignored) and in memory; the public listing
exposes a hint (``sk-****abcd``) + ``has_key`` only.
"""

import json
import os
import re
import threading
import uuid
from typing import Any

from app.engines.imagegen.providers import (
    BUILTIN_PROVIDER,
    PROVIDER_ORDER,
    PROVIDERS,
    provider_public,
)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
)
STORE_PATH = os.path.join(DATA_DIR, "image_providers.json")

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")

BUILTIN_SPEC = {
    "id": BUILTIN_PROVIDER,
    "label": "项目内置管线（默认）",
    "vendor": "CreativeForge",
    "models": ["artgen-2d"],
    "default_model": "artgen-2d",
    "default_size": "1024x1024",
    "credential_fields": [],
    "notes": "未选择任何外部 API 时，沿用项目现有的确定性 2D 生成内核。",
}


class ProviderStore:
    def __init__(self, path: str = STORE_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"selected": {"provider": BUILTIN_PROVIDER, "model": ""},
                                      "custom": [], "credentials": {}}
        self._load()

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                if isinstance(payload.get("selected"), dict):
                    self._data["selected"] = payload["selected"]
                if isinstance(payload.get("custom"), list):
                    self._data["custom"] = payload["custom"]
                if isinstance(payload.get("credentials"), dict):
                    self._data["credentials"] = payload["credentials"]
        except (OSError, ValueError):
            pass

    def _persist_locked(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            temporary = f"{self._path}.tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self._path)
            try:
                os.chmod(self._path, 0o600)
            except OSError:
                pass
        except OSError:
            pass

    # -- specs ----------------------------------------------------------

    def _custom_map(self) -> dict[str, dict[str, Any]]:
        return {item.get("id"): item for item in self._data["custom"] if item.get("id")}

    def all_specs(self) -> list[tuple[dict[str, Any], bool]]:
        specs: list[tuple[dict[str, Any], bool]] = [(BUILTIN_SPEC, False)]
        for pid in PROVIDER_ORDER:
            if pid in PROVIDERS:
                specs.append((PROVIDERS[pid], False))
        for item in self._data["custom"]:
            specs.append((item, True))
        return specs

    def get_spec(self, provider_id: str) -> dict[str, Any] | None:
        if provider_id == BUILTIN_PROVIDER:
            return BUILTIN_SPEC
        if provider_id in PROVIDERS:
            return PROVIDERS[provider_id]
        return self._custom_map().get(provider_id)

    def is_custom(self, provider_id: str) -> bool:
        return provider_id in self._custom_map()

    # -- credentials / selection ---------------------------------------

    def credentials(self, provider_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._data["credentials"].get(provider_id) or {})

    def save_credentials(self, provider_id: str, values: dict[str, Any]) -> None:
        with self._lock:
            bucket = dict(self._data["credentials"].get(provider_id) or {})
            for key, value in values.items():
                if value is None:
                    bucket.pop(key, None)
                elif str(value).strip():
                    bucket[key] = str(value).strip()
            self._data["credentials"][provider_id] = bucket
            self._persist_locked()

    def selected(self) -> dict[str, str]:
        with self._lock:
            return dict(self._data["selected"])

    def set_selected(self, provider: str, model: str | None = None) -> dict[str, str]:
        with self._lock:
            spec = self.get_spec(provider)
            if spec is None:
                provider = BUILTIN_PROVIDER
                spec = BUILTIN_SPEC
            self._data["selected"] = {
                "provider": provider,
                "model": (model or spec.get("default_model") or "").strip(),
            }
            self._persist_locked()
            return dict(self._data["selected"])

    # -- custom providers ----------------------------------------------

    def add_custom(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            base = str(payload.get("id") or payload.get("label") or "custom").lower()
            base = re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "custom"
            base = f"custom-{base}" if not base.startswith("custom") else base
            existing = self._custom_map()
            candidate = base
            while candidate in existing or candidate in PROVIDERS or candidate == BUILTIN_PROVIDER:
                candidate = f"{base}-{uuid.uuid4().hex[:4]}"
            spec = self._normalize_custom(candidate, payload)
            self._data["custom"].append(spec)
            self._persist_locked()
            return spec

    def update_custom(self, provider_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            for index, item in enumerate(self._data["custom"]):
                if item.get("id") == provider_id:
                    merged = dict(item)
                    merged.update(self._normalize_custom(provider_id, payload, base=item))
                    self._data["custom"][index] = merged
                    self._persist_locked()
                    return merged
            return None

    def delete_custom(self, provider_id: str) -> bool:
        with self._lock:
            before = len(self._data["custom"])
            self._data["custom"] = [
                item for item in self._data["custom"] if item.get("id") != provider_id
            ]
            self._data["credentials"].pop(provider_id, None)
            changed = len(self._data["custom"]) != before
            if changed:
                if self._data["selected"].get("provider") == provider_id:
                    self._data["selected"] = {"provider": BUILTIN_PROVIDER, "model": ""}
                self._persist_locked()
            return changed

    @staticmethod
    def _normalize_custom(provider_id: str, payload: dict[str, Any],
                          base: dict[str, Any] | None = None) -> dict[str, Any]:
        base = base or {}
        models = payload.get("models")
        if isinstance(models, str):
            models = [m.strip() for m in models.split(",") if m.strip()]
        if not models:
            models = base.get("models") or [payload.get("default_model") or "custom-model"]
        return {
            "id": provider_id,
            "label": str(payload.get("label") or base.get("label") or provider_id),
            "vendor": str(payload.get("vendor") or base.get("vendor") or "自定义"),
            "models": list(models),
            "default_model": str(payload.get("default_model") or models[0]),
            "default_size": str(payload.get("default_size") or base.get("default_size") or "1024x1024"),
            "size_format": str(payload.get("size_format") or base.get("size_format") or "x"),
            "endpoint": str(payload.get("endpoint") or base.get("endpoint") or ""),
            "method": str(payload.get("method") or base.get("method") or "POST").upper(),
            "auth": {
                "mode": str((payload.get("auth") or {}).get("mode")
                            or base.get("auth", {}).get("mode") or "bearer")
            },
            "credential_fields": list(
                payload.get("credential_fields")
                or base.get("credential_fields")
                or ["api_key"]
            ),
            "body": payload.get("body") or base.get("body")
            or {"model": "{model}", "prompt": "{prompt}", "size": "{size}"},
            "image_paths": list(
                payload.get("image_paths")
                or base.get("image_paths")
                or ["data.0.url", "data.0.b64_json"]
            ),
            "notes": str(payload.get("notes") or base.get("notes") or "用户自定义服务商。"),
        }

    # -- public listing -------------------------------------------------

    def public_listing(self) -> dict[str, Any]:
        with self._lock:
            providers = [
                provider_public(spec, self.credentials(spec["id"]), custom)
                for spec, custom in self.all_specs()
            ]
            return {
                "selected": self.selected(),
                "builtin_provider": BUILTIN_PROVIDER,
                "providers": providers,
            }


_store: ProviderStore | None = None


def get_store() -> ProviderStore:
    global _store
    if _store is None:
        _store = ProviderStore()
    return _store
