"""幂等键存储回归：同键复用、空键忽略、TTL 过期清理。"""

import unittest

from studio.backend.idempotency import IdempotencyStore


class IdempotencyStoreTests(unittest.TestCase):
    def test_same_key_returns_stored_value(self):
        store = IdempotencyStore()
        store.put("k1", {"task_id": "t1"})
        self.assertEqual(store.get("k1"), {"task_id": "t1"})

    def test_unknown_and_empty_keys_return_none(self):
        store = IdempotencyStore()
        self.assertIsNone(store.get("missing"))
        self.assertIsNone(store.get(None))
        self.assertIsNone(store.get(""))
        store.put(None, {"x": 1})  # 空键写入被忽略
        store.put("", {"x": 2})
        self.assertIsNone(store.get(None))
        self.assertIsNone(store.get(""))

    def test_expired_keys_are_pruned(self):
        now = {"t": 1000.0}
        store = IdempotencyStore(ttl=10.0, clock=lambda: now["t"])
        store.put("k1", "v")
        now["t"] += 11
        self.assertIsNone(store.get("k1"))

    def test_overwrite_keeps_latest_value(self):
        store = IdempotencyStore()
        store.put("k1", "first")
        store.put("k1", "second")
        self.assertEqual(store.get("k1"), "second")


if __name__ == "__main__":
    unittest.main()
