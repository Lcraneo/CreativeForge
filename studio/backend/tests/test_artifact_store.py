"""产物对象存储同步层的行为固（artifact_store）。

覆盖三条关键路径：
  1. 路径映射与越界拒绝（rel/abs 双向）；
  2. 本地缺失时按需回源，并写回本地缓存；
  3. 增量上传按 mtime+size 判重，且状态文件写进清单供启动回填。
"""

import os
import tempfile
import unittest
from unittest import mock

from studio.backend import artifact_store as store


class _MemoryProvider:
    """内存版 S3 兼容 provider：只实现本模块用到的 upload / download。"""

    def __init__(self):
        self.objects = {}
        self.uploads = []

    def upload(self, data, key, *, content_type="application/octet-stream"):
        self.objects[key] = data
        self.uploads.append(key)

    def download(self, key):
        if key not in self.objects:
            raise RuntimeError("NoSuchKey")
        return self.objects[key]


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.generated = os.path.join(self.tmp, "generated")
        self.data = os.path.join(self.tmp, "data")
        self.history = os.path.join(self.tmp, "history_service")
        for path in (self.generated, self.data, self.history):
            os.makedirs(path)
        self.provider = _MemoryProvider()
        self.patches = [
            mock.patch.object(store, "GENERATED_DIR", self.generated),
            mock.patch.object(store, "DATA_DIR", self.data),
            mock.patch.object(store, "HISTORY_DIR", self.history),
            mock.patch.object(store, "_provider", lambda: (self.provider, None)),
        ]
        for patch in self.patches:
            patch.start()
        store._index = {}
        store._manifest = set()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self._tmp.cleanup()

    def _write(self, rel, content=b"x"):
        path = store.abs_for(rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    # ── 路径映射 ────────────────────────────────────────────────────────────

    def test_rel_and_abs_roundtrip(self):
        path = os.path.join(self.generated, "img_1.png")
        self.assertEqual(store.rel_for(path), "generated/img_1.png")
        self.assertEqual(store.abs_for("generated/img_1.png"), path)

    def test_abs_rejects_traversal(self):
        self.assertIsNone(store.abs_for("generated/../../etc/passwd"))
        self.assertIsNone(store.abs_for("generated/.."))
        self.assertIsNone(store.abs_for("unknown/x.png"))

    # ── 回源 ────────────────────────────────────────────────────────────────

    def test_ensure_local_downloads_missing_file(self):
        rel = "generated/img_1.png"
        self.provider.objects["artifacts/" + rel] = b"png-bytes"
        path = store.ensure_local(rel)
        self.assertIsNotNone(path)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), b"png-bytes")

    def test_ensure_local_returns_existing_without_download(self):
        path = self._write("generated/img_1.png", b"local")
        self.assertEqual(store.ensure_local("generated/img_1.png"), path)
        self.assertEqual(self.provider.objects, {})

    def test_ensure_local_missing_remote_returns_none(self):
        self.assertIsNone(store.ensure_local("generated/absent.png"))

    # ── 上传 ────────────────────────────────────────────────────────────────

    def test_upload_skips_secret_and_tmp(self):
        self._write("data/.storage_secret", b"key")
        self._write("data/storage_configs.json", b"{}")
        self.assertFalse(store.upload_file(os.path.join(self.data, ".storage_secret")))
        self.assertFalse(store.upload_file(os.path.join(self.data, "storage_configs.json")))
        self.assertEqual(self.provider.uploads, [])

    def test_upload_dedupes_by_stat(self):
        path = self._write("generated/img_1.png", b"abc")
        os.utime(path, (1.0, 1.0))
        self.assertTrue(store.upload_file(path))
        self.assertFalse(store._needs_upload("generated/img_1.png", path))
        self.assertEqual(self.provider.uploads, ["artifacts/generated/img_1.png"])

    def test_upload_marks_json_as_state(self):
        path = self._write("data/scenes/scenes.json", b'{"scenes": []}')
        os.utime(path, (1.0, 1.0))
        self.assertTrue(store.upload_file(path))
        self.assertIn("data/scenes/scenes.json", store._manifest)
        store._flush_manifest(self.provider)
        self.assertIn(store._MANIFEST_KEY, self.provider.objects)

    # ── 启动回填 ────────────────────────────────────────────────────────────

    def test_restore_state_uses_manifest(self):
        payload = b'{"state_files": ["history/history.json"], "updated_at": 0}'
        self.provider.objects[store._MANIFEST_KEY] = payload
        self.provider.objects["artifacts/history/history.json"] = b"[]"
        restored = store.restore_state()
        self.assertEqual(restored, 1)
        self.assertTrue(os.path.isfile(os.path.join(self.history, "history.json")))

    def test_restore_state_without_manifest_is_noop(self):
        self.assertEqual(store.restore_state(), 0)

    def test_restore_state_skips_existing_file(self):
        self._write("history/history.json", b"local")
        self.provider.objects[store._MANIFEST_KEY] = (
            b'{"state_files": ["history/history.json"]}'
        )
        self.provider.objects["artifacts/history/history.json"] = b"remote"
        self.assertEqual(store.restore_state(), 0)
        with open(os.path.join(self.history, "history.json"), "rb") as handle:
            self.assertEqual(handle.read(), b"local")

    # ── 扫描 ────────────────────────────────────────────────────────────────

    def test_scan_uploads_new_artifacts_only(self):
        old = self._write("generated/img_old.png", b"old")
        os.utime(old, (1.0, 1.0))
        store._index = {}
        uploads = store._scan_once(self.provider)
        self.assertEqual(uploads, 1)
        self.assertIn("artifacts/generated/img_old.png", self.provider.objects)

    def test_scan_skips_freshly_written_file(self):
        fresh = self._write("generated/img_new.png", b"new")
        # mtime 在 settle 窗口内，视为可能仍在写入，本轮不传
        self.assertFalse(store._needs_upload("generated/img_new.png", fresh))


if __name__ == "__main__":
    unittest.main()
