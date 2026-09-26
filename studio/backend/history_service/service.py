"""Persistent generation history (falls back gracefully when the disk is read-only).

Every finished (or failed) production task is appended as a record containing
the prompt, timestamps, engine, quality scores, the character spec and a full
CreativeAsset snapshot — so users can revisit any past generation even after a
server restart, regardless of the in-memory asset store.
"""

import json
import os
import threading
import time

DEFAULT_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "history.json"
)

MAX_RECORDS = 300


class HistoryStore:
    def __init__(self, path=DEFAULT_HISTORY_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._records = []
        self._counter = 0
        self._load()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            payload = {}

        records = payload.get("records") if isinstance(payload, dict) else None
        self._records = records if isinstance(records, list) else []
        self._counter = int(payload.get("counter", len(self._records))) if isinstance(payload, dict) else len(self._records)

    def _persist_locked(self):
        try:
            directory = os.path.dirname(self._path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            temporary = "{}.tmp".format(self._path)
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(
                    {"counter": self._counter, "records": self._records},
                    handle,
                    ensure_ascii=False,
                    indent=2
                )
            os.replace(temporary, self._path)
        except OSError:
            # read-only deployment: keep serving from memory
            pass

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def add(self, record):
        with self._lock:
            self._counter += 1
            item = dict(record)
            item["record_id"] = "H{:04d}".format(self._counter)
            item.setdefault("finished_at", time.time())
            self._records.append(item)
            if len(self._records) > MAX_RECORDS:
                self._records = self._records[-MAX_RECORDS:]
            self._persist_locked()
            return item["record_id"]

    def list(self, limit=100, engine=None, keyword=None):
        with self._lock:
            items = self._records
            if engine:
                items = [item for item in items if item.get("engine") == engine]
            if keyword:
                needle = str(keyword).lower()
                items = [
                    item for item in items
                    if needle in str(item.get("goal", "")).lower()
                    or needle in str(item.get("name", "")).lower()
                    or needle in str((item.get("character") or {}).get("summary", "")).lower()
                ]
            ordered = sorted(
                items,
                key=lambda item: item.get("finished_at", item.get("created_at", 0)),
                reverse=True
            )
            return [self._summary(item) for item in ordered[: max(1, int(limit))]]

    def get(self, record_id):
        with self._lock:
            for item in self._records:
                if item.get("record_id") == record_id:
                    return dict(item)
            return None

    def clear(self):
        with self._lock:
            self._records = []
            self._counter = 0
            self._persist_locked()

    def count(self):
        with self._lock:
            return len(self._records)

    @staticmethod
    def _summary(item):
        character = item.get("character") or {}
        return {
            "record_id": item.get("record_id"),
            "task_id": item.get("task_id"),
            "created_at": item.get("created_at"),
            "finished_at": item.get("finished_at"),
            "goal": item.get("goal"),
            "engine": item.get("engine"),
            "status": item.get("status"),
            "report_status": item.get("report_status"),
            "asset_id": item.get("asset_id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "role": item.get("role"),
            "action": item.get("action"),
            "frames": item.get("frames"),
            "fps": item.get("fps"),
            "scores": item.get("scores") or {},
            "qa_rounds": item.get("qa_rounds", 0),
            "elapsed_seconds": item.get("elapsed_seconds"),
            "error": item.get("error"),
            "image": item.get("image"),
            "enhanced_prompt": item.get("enhanced_prompt"),
            "character": {
                "summary": character.get("summary"),
                "gender_label": character.get("gender_label"),
                "class_label": character.get("class_label"),
                "element_label": character.get("element_label"),
                "role_label": character.get("role_label"),
                "hair_color_hex": character.get("hair_color_hex"),
                "hair_color_label": character.get("hair_color_label"),
                "hair_style_label": character.get("hair_style_label"),
                "skin_hex": character.get("skin_hex"),
                "eyes_hex": character.get("eyes_hex"),
                "expression_label": character.get("expression_label"),
                "build_label": character.get("build_label"),
                "height_cm": character.get("height_cm"),
                "weapon_label": character.get("weapon_label"),
                "accessory": character.get("accessory") or [],
                "seed": character.get("seed"),
            },
            "palette": item.get("palette") or [],
        }
