"""Persistence for user-defined action presets (动作自定义配置).

Each preset captures everything needed to reproduce a motion:
``{name, description, action, view, pose_config}`` plus provenance metadata
(``created_at`` / ``updated_at`` / ``revision`` / ``history``) so custom
actions survive restarts, stay editable in place and keep a traceable
modification history.
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

    def list(self, include_history: bool = False) -> list[dict[str, Any]]:
        # 默认投影掉 history 快照（每条最多 12 份旧参数，列表/导出用不上）；
        # 详情走 get() 拿完整记录
        items = sorted(
            self._actions.values(), key=lambda item: item.get("updated_at", 0), reverse=True
        )
        if include_history:
            return items
        return [
            {key: value for key, value in item.items() if key != "history"} for item in items
        ]

    def save(self, payload: dict[str, Any], trigger: str = "edit") -> dict[str, Any]:
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
        # 编辑落点解析：original_name 指向「正在被编辑的旧记录」——同名就地
        # 修改时等于 name，改名时指向旧名。改名须旧记录存在、新名不与其他
        # 动作撞车；元数据（创建时间/版本数/历史）随记录迁移，改名不会被
        # 当成「删旧建新」丢掉溯源。
        original = str(payload.get("original_name") or "")
        source = self._actions.get(original) if original else None
        if original and source is None:
            raise ValueError("原动作不存在或已被删除，无法保存修改")
        if original and original != name and name in self._actions:
            raise ValueError("已存在同名动作，请换一个名称")
        if original and original != name:
            del self._actions[original]
        base = source or self._actions.get(name)
        now = time.time()
        revision = (int(base.get("revision", 1)) + 1) if base else 1
        history: list[dict[str, Any]] = list(base.get("history", [])) if base else []
        if base:
            # 修改历史：覆盖前留一份旧版本快照（最新在前、封顶 12 条）——
            # 「改坏了想找回」与「参数怎么演化」都可追溯
            history.insert(
                0,
                {
                    "time": now,
                    "trigger": trigger,
                    "revision": int(base.get("revision", 1)),
                    "action": base.get("action"),
                    "view": base.get("view"),
                    "pose_config": base.get("pose_config"),
                    "description": base.get("description", ""),
                },
            )
            del history[12:]
        clean = {
            "name": name,
            "action": str(payload.get("action") or "walk"),
            "view": payload.get("view") if payload.get("view") in ("front", "side") else "front",
            "description": str(payload.get("description") or "").strip()[:500],
            "pose_config": clean_config,
            "created_at": base.get("created_at", now) if base else now,
            "updated_at": now,
            "revision": revision,
            "history": history,
        }
        self._actions[name] = clean
        self._flush()
        return clean

    def get(self, name: str) -> dict[str, Any] | None:
        return self._actions.get(name)

    def delete(self, name: str) -> bool:
        if name in self._actions:
            del self._actions[name]
            self._flush()
            return True
        return False
