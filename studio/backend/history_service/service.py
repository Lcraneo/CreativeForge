"""Persistent store of past generations (prompt + character + asset snapshot).

Each finished Studio task is appended here so the History view survives
restarts. Records are kept in a single JSON file keyed by ``task_id``.
"""

import json
import os
import threading

DEFAULT_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "history.json"
)


class HistoryStore:
    def __init__(self, path=None):
        self.path = path or DEFAULT_HISTORY_PATH
        self._lock = threading.Lock()
        self._records = []
        self._load()

    def _load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                self._records = data if isinstance(data, list) else []
            except (ValueError, OSError):
                self._records = []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(self._records, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def add(self, record):
        """Append a history record and return its id.

        Ids are de-duplicated on insert: task counters restart between
        backend runs, so a bare ``task_id`` is not unique across sessions.
        """

        if not isinstance(record, dict):
            return None
        record = dict(record)
        with self._lock:
            existing = {r.get("id") for r in self._records}
            rid = record.get("id") or record.get("task_id") or "H{:04d}".format(
                len(self._records) + 1
            )
            if rid in existing:
                suffix = 2
                while "{}-{}".format(rid, suffix) in existing:
                    suffix += 1
                rid = "{}-{}".format(rid, suffix)
            record["id"] = rid
            self._records.append(record)
            self._save()
        return rid

    def get(self, record_id):
        with self._lock:
            for record in self._records:
                if record.get("id") == record_id:
                    return record
            for record in self._records:
                if record.get("task_id") == record_id:
                    return record
        return None

    def list(self, limit=100, engine=None, keyword=None):
        with self._lock:
            items = list(self._records)
        items.sort(
            key=lambda r: r.get("finished_at", r.get("created_at", 0)),
            reverse=True,
        )
        if engine:
            items = [r for r in items if r.get("engine") == engine]
        if keyword:
            needle = str(keyword).lower()
            items = [r for r in items if needle in str(r.get("goal", "")).lower()]
        return items[:limit]

    def count(self):
        with self._lock:
            return len(self._records)

    def clear(self):
        with self._lock:
            self._records = []
            self._save()

    def patch_asset(self, asset_id, patch):
        """Merge ``patch`` into the asset payload of the matching record.

        Returns True when a record was found and updated."""

        with self._lock:
            for record in self._records:
                if record.get("id") == asset_id or record.get("task_id") == asset_id:
                    asset = record.get("asset")
                    if isinstance(asset, dict):
                        asset.update(patch)
                        record["asset"] = asset
                        self._save()
                        return True
        return False

    def delete(self, record_id):
        """Remove the single record whose id matches exactly; returns count removed."""

        with self._lock:
            before = len(self._records)
            self._records = [
                record for record in self._records if record.get("id") != record_id
            ]
            removed = before - len(self._records)
            if removed:
                self._save()
            return removed
