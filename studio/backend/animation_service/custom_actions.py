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
        # 数值参数直存；phases（多段编排）逐段校验后保留——静默丢弃会让
        # 「先…然后…」类编排动作保存后退化成单一循环
        clean_config: dict[str, Any] = {}
        for key, value in config.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                clean_config[key] = value
            elif key == "phases" and isinstance(value, list):
                phases = []
                for seg in value[:5]:
                    if not isinstance(seg, dict):
                        continue
                    act = str(seg.get("action") or "")
                    if act not in ("idle", "walk", "run", "attack", "jump"):
                        continue
                    try:
                        weight = max(0.5, min(4.0, float(seg.get("weight", 1.0) or 1.0)))
                        turn = max(0.0, min(180.0, float(seg.get("turn", 0) or 0.0)))
                    except (TypeError, ValueError):
                        continue
                    phases.append({"action": act, "weight": weight, "turn": turn})
                if len(phases) >= 2:
                    clean_config["phases"] = phases
        clean = {
            "name": name,
            "action": str(payload.get("action") or "walk"),
            "view": payload.get("view") if payload.get("view") in ("front", "side") else "front",
            "pose_config": clean_config,
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
