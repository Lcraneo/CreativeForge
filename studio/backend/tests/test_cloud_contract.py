"""S1 骨架回归：契约扩展、运行开关、厂商目录、凭据存储。

覆盖实施计划的契约规则 R1–R10 中可在骨架期验证的部分：
R2（缺省即合法）、R3（未知字段忽略）、R5（路径沙箱）、R7（失败留痕）、
R8（导出净化），以及配置面的脱敏与凭据来源优先级。

运行：``python -m unittest studio.backend.tests.test_cloud_contract -v``
"""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.cloud_backends import config, sidecar
from adapters.cloud_backends.contracts import extension_v1 as contract
from studio.backend.cloud_service import catalog
from studio.backend.cloud_service.provider_store import (
    CloudProviderStore,
    CloudProviderStoreError,
)

HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None


def _succeeded_mesh(**overrides):
    slot = {
        "status": "succeeded",
        "provider": "tripo",
        "task_id": "task_abc",
        "format": "glb",
        "local_path": "cloud/mesh/2026-10-22/task_abc.glb",
        "bytes": 1024,
        "sha256": "a" * 64,
    }
    slot.update(overrides)
    return slot


def _block(**slots):
    block = {"version": "1.0"}
    block.update(slots)
    return block


class ExtensionContractTests(unittest.TestCase):
    # R2 ────────────────────────────────────────────────────────────────
    def test_extension_is_optional(self):
        asset = {"identity": {"id": "a1"}, "version": {"schema": "1.0"}}
        self.assertIsNone(contract.read_extension(asset))
        self.assertEqual(contract.validate(None), [])
        self.assertEqual(contract.normalize(None), {})

    def test_empty_asset_is_valid(self):
        self.assertEqual(contract.validate({}), [])

    # R3 ────────────────────────────────────────────────────────────────
    def test_unknown_fields_are_ignored(self):
        block = _block(
            mesh=_succeeded_mesh(provider_note="ignored", extra={"x": 1}),
            future_slot={"status": "succeeded"},
        )
        self.assertEqual(contract.validate(block), [])
        clean = contract.normalize(block)
        self.assertNotIn("future_slot", clean)
        self.assertNotIn("provider_note", clean["mesh"])
        self.assertNotIn("extra", clean["mesh"])

    def test_unknown_top_level_key_ignored(self):
        self.assertEqual(contract.validate(_block(notes="hello")), [])

    def test_major_version_mismatch_reported(self):
        issues = contract.validate({"version": "2.0"})
        self.assertTrue(any("主版本不兼容" in item for item in issues))

    # 状态与必填 ────────────────────────────────────────────────────────
    def test_invalid_status_reported(self):
        issues = contract.validate(_block(mesh={"status": "done"}))
        self.assertTrue(any("status 非法" in item for item in issues))

    def test_succeeded_requires_provider_and_path(self):
        issues = contract.validate(_block(mesh={"status": "succeeded", "sha256": "a" * 64}))
        self.assertTrue(any("缺少合法 provider" in item for item in issues))
        self.assertTrue(any("缺少合法 local_path" in item for item in issues))

    def test_unknown_provider_reported(self):
        issues = contract.validate(_block(mesh=_succeeded_mesh(provider="unknown")))
        self.assertTrue(any("未登记" in item for item in issues))

    # R5 ────────────────────────────────────────────────────────────────
    def test_absolute_path_rejected(self):
        for bad in ("/etc/passwd", "C:/temp/a.glb", "\\\\server\\share\\a.glb"):
            self.assertIsNone(contract.safe_rel_path(bad), bad)

    def test_parent_traversal_rejected(self):
        self.assertIsNone(contract.safe_rel_path("../secret.glb"))
        self.assertIsNone(contract.safe_rel_path("cloud/../../secret.glb"))

    def test_safe_path_is_normalized(self):
        self.assertEqual(contract.safe_rel_path("./cloud//a.glb"), "cloud/a.glb")
        self.assertEqual(contract.safe_rel_path("cloud\\a.glb"), "cloud/a.glb")

    def test_resolve_inside_root(self):
        with tempfile.TemporaryDirectory() as root:
            resolved = contract.resolve_local_path("cloud/a.glb", root=root)
            self.assertTrue(resolved.startswith(os.path.abspath(root)))
            self.assertEqual(os.path.basename(resolved), "a.glb")

    def test_resolve_outside_root_raises(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(contract.CloudExtensionError):
                contract.resolve_local_path("../a.glb", root=root)

    # R7 ────────────────────────────────────────────────────────────────
    def test_failed_slot_keeps_only_trace(self):
        block = _block(
            video={
                "status": "failed",
                "provider": "ark",
                "error_class": "quota",
                "error_message": "insufficient credits",
                "local_path": "cloud/video/partial.mp4",
                "sha256": "b" * 64,
            }
        )
        self.assertEqual(contract.validate(block), [])
        clean = contract.normalize(block)
        self.assertEqual(
            set(clean["video"]), {"status", "provider", "error_class", "error_message"}
        )

    def test_failed_requires_error_class(self):
        issues = contract.validate(_block(video={"status": "failed", "provider": "ark"}))
        self.assertTrue(any("error_class" in item for item in issues))

    def test_error_slot_helper(self):
        slot = contract.error_slot("ark", "rate_limit", "slow down")
        self.assertEqual(slot["status"], "failed")
        self.assertEqual(slot["error_class"], "rate_limit")
        with self.assertRaises(contract.CloudExtensionError):
            contract.error_slot("ark", "boom")

    # R1 / R8 ───────────────────────────────────────────────────────────
    def test_write_preserves_existing_fields(self):
        asset = {
            "identity": {"id": "a1"},
            "pixel": {"grid": {"size": 16}},
            "version": {"schema": "1.0"},
        }
        contract.write_extension(asset, _block(mesh=_succeeded_mesh()))
        self.assertEqual(asset["identity"], {"id": "a1"})
        self.assertEqual(asset["pixel"], {"grid": {"size": 16}})
        self.assertIn("cloud_backends", asset["extensions"])
        self.assertEqual(contract.validate(contract.read_extension(asset)), [])

    def test_write_does_not_create_empty_shell(self):
        asset = {"identity": {"id": "a1"}}
        contract.write_extension(asset, {"version": "1.0"})
        self.assertNotIn("extensions", asset)

    def test_write_rejects_non_dict(self):
        with self.assertRaises(contract.CloudExtensionError):
            contract.write_extension([], {})

    def test_export_view_strips_provenance(self):
        block = _block(
            mesh=_succeeded_mesh(),
            provenance={"request_hash": "sha256:abc", "cache_hit": False},
        )
        view = contract.export_view(block)
        self.assertNotIn("provenance", view)
        self.assertIn("mesh", view)

    def test_provenance_keeps_gf_caliber_fields_and_export_still_strips(self):
        """GF last_call_info 口径字段可落 provenance；R8 导出剥离行为不变。"""

        block = _block(
            mesh=_succeeded_mesh(),
            provenance={
                "request_hash": "sha256:abc",
                "created_at": "2026-10-23T00:00:00Z",
                "cache_hit": False,
                "credits_estimate": 20,
                "elapsed_sec": 1.5,
                "preview_url": "https://cdn.example.com/render.png",
                "triangles": 12000,
            },
        )
        self.assertEqual(contract.validate(block), [])
        clean = contract.normalize(block)
        provenance = clean["provenance"]
        self.assertEqual(provenance["elapsed_sec"], 1.5)
        self.assertEqual(provenance["preview_url"], "https://cdn.example.com/render.png")
        self.assertEqual(provenance["triangles"], 12000)
        self.assertEqual(provenance["credits_estimate"], 20)
        # 旧字段名保持不变（R8：导出仍剥离 provenance 整体）
        view = contract.export_view(block)
        self.assertNotIn("provenance", view)

    def test_provenance_rejects_non_numeric_elapsed(self):
        block = _block(
            provenance={"request_hash": "sha256:abc", "elapsed_sec": "soon"},
        )
        issues = contract.validate(block)
        self.assertTrue(any("elapsed_sec" in item for item in issues))

    def test_invalid_block_type_reported(self):
        issues = contract.validate([1, 2])
        self.assertTrue(issues)


class CloudConfigTests(unittest.TestCase):
    def test_defaults_are_safe(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(config.cloud_enabled())
            self.assertFalse(config.sidecar_enabled())
            self.assertEqual(config.cache_ttl_seconds(), 7 * 24 * 3600)
            self.assertEqual(config.cache_max_bytes(), 500 * 1024 * 1024)
            self.assertEqual(config.request_timeout(), 60)
            self.assertEqual(config.max_retries(), 3)

    def test_toggle_off(self):
        with mock.patch.dict(
            os.environ,
            {"CF_CLOUD_BACKENDS": "off", "CF_SIDECAR_ENABLED": "1"},
            clear=True,
        ):
            self.assertFalse(config.cloud_enabled())
            self.assertTrue(config.sidecar_enabled())

    def test_cache_dir_override(self):
        with tempfile.TemporaryDirectory() as root:
            with mock.patch.dict(os.environ, {"CF_CLOUD_CACHE_DIR": root}, clear=True):
                self.assertEqual(config.cache_dir(), os.path.abspath(root))
                snapshot = config.settings_snapshot()
                self.assertEqual(snapshot["cache_ttl_days"], 7)
                self.assertEqual(snapshot["cache_max_mb"], 500)

    def test_sidecar_seam_is_closed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(sidecar.enabled())
            self.assertFalse(sidecar.available())
            with self.assertRaises(sidecar.SidecarUnavailable):
                sidecar.require("local_3d_object")
            with self.assertRaises(sidecar.SidecarUnavailable):
                sidecar.require("unknown_kind")


class CatalogTests(unittest.TestCase):
    def test_every_provider_declares_known_slots(self):
        for pid, spec in catalog.PROVIDER_CATALOG.items():
            self.assertIn(spec["slot"], contract.SLOT_NAMES, pid)
            self.assertIn(spec["protocol"], ("sync", "async"), pid)
            self.assertTrue(spec["capabilities"], pid)

    def test_3d_channels_are_ordered_bailian_then_tripo_then_meshy(self):
        # 主通道走项目已有的阿里云 Key，其次 Tripo 官方，最后 Meshy 兜底
        self.assertEqual(
            catalog.providers_for("gen_3d_object_cloud"),
            ["bailian-tripo", "tripo", "meshy"],
        )
        self.assertEqual(catalog.PROVIDER_CATALOG["bailian-tripo"]["fallback"], "tripo")
        self.assertEqual(catalog.PROVIDER_CATALOG["tripo"]["fallback"], "meshy")
        self.assertEqual(catalog.PROVIDER_CATALOG["meshy"]["fallback"], "")

    def test_bailian_reuses_dashscope_credential(self):
        ref = catalog.PROVIDER_CATALOG["bailian-tripo"]["credential_ref"]
        self.assertEqual(ref, "model_settings:dashscope:api_key")
        # WorkspaceId 无法复用，必须作为额外字段单独配置
        self.assertIn("workspace_id", catalog.PROVIDER_CATALOG["bailian-tripo"]["extra_fields"])

    def test_ark_reuses_model_settings_credential(self):
        ref = catalog.PROVIDER_CATALOG["ark"]["credential_ref"]
        self.assertEqual(ref, "model_settings:volcengine:api_key")

    def test_public_catalog_exposes_no_secret(self):
        payload = json.dumps(catalog.public_catalog(), ensure_ascii=False)
        self.assertNotIn("api_key=", payload)
        for item in catalog.public_catalog():
            self.assertNotIn("api_key", item)


class ProviderStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        self.path = str(base / "cloud_providers.json")
        self.secret = str(base / ".cloud_secret")
        self.settings = {"provider": "volcengine", "api_key": "ark-key-from-store"}
        self.store = CloudProviderStore(
            path=self.path,
            secret_file=self.secret,
            settings_provider=lambda: dict(self.settings),
        )

    def test_unknown_provider_rejected(self):
        with self.assertRaises(CloudProviderStoreError):
            self.store.save("nope", {"enabled": True})
        with self.assertRaises(CloudProviderStoreError):
            self.store.resolve_key("nope")

    def test_save_roundtrip_and_reload(self):
        self.store.save("tripo", {"enabled": False, "model": "v2.5"})
        reloaded = CloudProviderStore(
            path=self.path, secret_file=self.secret, settings_provider=lambda: {}
        )
        view = reloaded.public("tripo")
        self.assertFalse(view["enabled"])
        self.assertEqual(view["model"], "v2.5")
        self.assertFalse(view["has_key"])

    def test_unknown_field_ignored(self):
        self.store.save("tripo", {"enabled": True, "api_key": "should-not-persist"})
        with open(self.path, encoding="utf-8") as handle:
            raw = handle.read()
        self.assertNotIn("should-not-persist", raw)

    def test_invalid_type_rejected(self):
        with self.assertRaises(CloudProviderStoreError):
            self.store.save("tripo", {"enabled": "yes"})
        with self.assertRaises(CloudProviderStoreError):
            self.store.save("tripo", {"base_url": 123})

    def test_env_key_takes_priority(self):
        with mock.patch.dict(os.environ, {"TRIPO_API_KEY": "env-token"}, clear=True):
            key, source = self.store.resolve_key("tripo")
        self.assertEqual((key, source), ("env-token", "env"))

    def test_credential_ref_reuse(self):
        key, source = self.store.resolve_key("ark")
        self.assertEqual((key, source), ("ark-key-from-store", "credential_ref"))
        view = self.store.public("ark")
        self.assertTrue(view["has_key"])
        self.assertEqual(view["key_source"], "credential_ref")
        self.assertNotEqual(view["key_hint"], "ark-key-from-store")

    def test_credential_ref_ignored_when_provider_differs(self):
        self.settings = {"provider": "dashscope", "api_key": "other"}
        self.assertEqual(self.store.resolve_key("ark"), ("", ""))

    def test_workspace_id_renders_base_url(self):
        view = self.store.public("bailian-tripo")
        # 未配置时保留模板，并把它列为缺失字段（供前端提示）
        self.assertIn("{workspace_id}", view["base_url"])
        self.assertIn("workspace_id", view["missing_fields"])
        self.assertFalse(view["configured"])

        self.store.save("bailian-tripo", {"workspace_id": "ws-123"})
        view = self.store.public("bailian-tripo")
        self.assertEqual(view["base_url"], "https://ws-123.cn-beijing.maas.aliyuncs.com")
        self.assertEqual(view["missing_fields"], [])

    def test_bailian_ready_when_dashscope_configured(self):
        self.settings = {"provider": "dashscope", "api_key": "dash-key"}
        self.store.save("bailian-tripo", {"workspace_id": "ws-123"})
        view = self.store.public("bailian-tripo")
        self.assertTrue(view["has_key"])
        self.assertEqual(view["key_source"], "credential_ref")
        self.assertTrue(view["configured"])
        self.assertTrue(self.store.readiness()["gen_3d_object_cloud"])

    def test_masked_view_never_returns_plaintext(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            view = self.store.public("ark")
        self.assertNotIn("ark-key-from-store", json.dumps(view))

    def test_readiness_reflects_configuration(self):
        readiness = self.store.readiness()
        self.assertTrue(readiness["gen_image_cloud"])  # ARK 已通过复用就绪
        self.assertFalse(readiness["gen_3d_object_cloud"])  # Tripo 未配置

    @unittest.skipUnless(HAS_CRYPTO, "需要 cryptography 依赖")
    def test_key_is_encrypted_at_rest(self):
        self.store.set_key("tripo", "tripo-secret-value")
        with open(self.path, encoding="utf-8") as handle:
            raw = handle.read()
        self.assertNotIn("tripo-secret-value", raw)
        self.assertTrue(os.path.isfile(self.secret))
        key, source = self.store.resolve_key("tripo")
        self.assertEqual((key, source), ("tripo-secret-value", "store"))
        self.store.clear_key("tripo")
        self.assertEqual(self.store.resolve_key("tripo"), ("", ""))

    @unittest.skipIf(HAS_CRYPTO, "仅验证缺少依赖时的显式报错")
    def test_missing_crypto_raises_clear_error(self):
        with self.assertRaises(CloudProviderStoreError) as ctx:
            self.store.set_key("tripo", "tripo-secret-value")
        self.assertIn("cryptography", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
