"""Persistence for user-defined action presets (动作自定义配置).

Each preset captures everything needed to reproduce a motion:
``{name, action, view, pose_config}`` — saved/loaded from a JSON file so
custom actions survive restarts and can be reused across sessions.
"""

import json
import os
import time
from typing import Any


class CustomActionStore:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._actions: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _flush(self) -> None:
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self._actions, handle, ensure_ascii=False, indent=2)

    def list(self) -> list[dict[str, Any]]:
        return sorted(
            self._actions.values(), key=lambda item: item.get("updated_at", 0), reverse=True
        )

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("动作名称不能为空")
        if len(name) > 40:
            raise ValueError("动作名称过长（最多 40 字符）")
        config = payload.get("pose_config")
        if not isinstance(config, dict):
            raise ValueError("pose_config 必须是对象")
        clean = {
            "name": name,
            "action": str(payload.get("action") or "walk"),
            "view": payload.get("view") if payload.get("view") in ("front", "side") else "front",
            "pose_config": {k: v for k, v in config.items() if isinstance(v, (int, float))},
            "updated_at": time.time(),
            "created_at": self._actions.get(name, {}).get("created_at", time.time()),
        }
        self._actions[name] = clean
        self._flush()
        return clean

    def delete(self, name: str) -> bool:
        if name in self._actions:
            del self._actions[name]
            self._flush()
            return True
        return False
