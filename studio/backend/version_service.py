"""Asset version control (P1-A): version tree + rollback with audit log.

版本树按角色名（history record ``name``）分组：同名记录即同一资产的不同
版本，按完成时间升序编为 v1..vn。回滚 = 把历史快照重新存为当前资产，
并写入可落盘的回滚审计日志（rollbacks.json），回答「改坏了怎么办」。
"""

import json
import os
import threading
import time

DEFAULT_ROLLBACKS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rollbacks.json")


class VersionService:
    def __init__(self, path=None):
        self.path = path or DEFAULT_ROLLBACKS_PATH
        self._lock = threading.Lock()
        self._rollbacks = []
        self._load()

    # -- audit log -------------------------------------------------------

    def _load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                self._rollbacks = data if isinstance(data, list) else []
            except (ValueError, OSError):
                self._rollbacks = []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(self._rollbacks, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def log_rollback(self, entries):
        """entries: [{record_id, asset_id, name, version_no}] — one audit row
        per rollback operation (single or batch)."""

        record = {
            "id": "RB{:04d}".format(len(self._rollbacks) + 1),
            "at": time.time(),
            "count": len(entries),
            "entries": entries,
        }
        with self._lock:
            self._rollbacks.append(record)
            self._save()
        return record

    def rollback_log(self, limit=50):
        with self._lock:
            items = list(self._rollbacks)
        items.reverse()
        return items[:limit]

    # -- version tree ------------------------------------------------------

    @staticmethod
    def groups(history, limit=50):
        """All character groups (name -> version count), newest first."""

        buckets = {}
        for record in history.list(limit=500):
            name = record.get("name") or "未命名资产"
            bucket = buckets.setdefault(name, {"name": name, "count": 0, "latest_at": 0})
            bucket["count"] += 1
            bucket["latest_at"] = max(
                bucket["latest_at"], record.get("finished_at", record.get("created_at", 0))
            )
        groups = sorted(buckets.values(), key=lambda g: g["latest_at"], reverse=True)
        return groups[:limit]

    @staticmethod
    def _version_view(record, version_no):
        image = record.get("image") or {}
        asset = record.get("asset") or {}
        asset_image = asset.get("image") or {}
        character = record.get("character") or {}
        scores = record.get("scores") or {}
        palette = (asset.get("pixel") or {}).get("palette") or {}
        return {
            "version_no": version_no,
            "record_id": record.get("id"),
            "asset_id": record.get("asset_id") or asset.get("id"),
            "task_id": record.get("task_id"),
            "name": record.get("name"),
            "created_at": record.get("finished_at", record.get("created_at")),
            "engine": record.get("engine"),
            "seed": character.get("seed"),
            "action": record.get("action"),
            "status": record.get("report_status") or record.get("status"),
            "image_url": image.get("url") or asset_image.get("url"),
            "scores": {
                "pixel": scores.get("pixel"),
                "animation": scores.get("animation"),
                "engine": scores.get("engine"),
            },
            "palette": palette.get("colors") or [],
            "goal": record.get("goal"),
            "review_tag": record.get("review_tag"),
        }

    @classmethod
    def tree(cls, history, name):
        """One character's version tree, oldest -> newest (v1..vn)."""

        records = [
            record
            for record in history.list(limit=500)
            if (record.get("name") or "未命名资产") == name
        ]
        records.sort(key=lambda r: r.get("finished_at", r.get("created_at", 0)))
        versions = [cls._version_view(record, i + 1) for i, record in enumerate(records)]
        return {
            "name": name,
            "count": len(versions),
            "latest": versions[-1] if versions else None,
            "versions": versions,
        }

    @staticmethod
    def diff(tree, version_a, version_b):
        """Field-level diff between two version numbers of one tree."""

        by_no = {v["version_no"]: v for v in tree["versions"]}
        va, vb = by_no.get(version_a), by_no.get(version_b)
        if not va or not vb:
            return None
        fields = []
        for key, label in (
            ("seed", "随机种子 Seed"),
            ("engine", "目标引擎"),
            ("action", "动作"),
            ("status", "质量结论"),
        ):
            if va.get(key) != vb.get(key):
                fields.append({"field": label, "a": va.get(key), "b": vb.get(key)})
        pa, pb = set(va.get("palette") or []), set(vb.get("palette") or [])
        if pa != pb:
            fields.append(
                {
                    "field": "调色板变化",
                    "a": "、".join(sorted(pa - pb)) or "—",
                    "b": "、".join(sorted(pb - pa)) or "—",
                }
            )
        for key, label in (("pixel", "像素分"), ("animation", "动画分"), ("engine", "引擎分")):
            sa, sb = va["scores"].get(key), vb["scores"].get(key)
            if sa is not None and sb is not None and round(sa, 3) != round(sb, 3):
                fields.append(
                    {
                        "field": label,
                        "a": "{:.0%}".format(sa),
                        "b": "{:.0%}".format(sb),
                    }
                )
        return {"a": va, "b": vb, "fields": fields}
