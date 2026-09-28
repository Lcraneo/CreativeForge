"""对象存储模块离线自测（无网络依赖）。

运行：``python -m studio.backend.storage_service.__main__``

覆盖：加密存储往返、脱敏 / redact、配置 CRUD 与默认切换、端点解析、
分片上传状态机（含断点续传对账、失败重试、越界与大小校验）。
真实连通性请通过 API 配置页的「测试连接」完成。
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from .interface import (
    StorageConfig,
    StorageConfigError,
    StorageTimeoutError,
    mask_secret,
    redact,
)
from .providers import resolve_endpoint
from .settings import StorageConfigStore
from .transfer import MultipartManager


class FakeProvider:
    """分片端口的假实现：模拟远端分片表 + 可注入的失败。"""

    def __init__(self):
        self.uploads: dict[str, dict] = {}
        self.fail_next = 0  # >0 时 upload_part 失败 N 次（测重试）

    def create_multipart_upload(self, key, *, content_type="application/octet-stream"):
        upload_id = f"fake-up-{len(self.uploads)}"
        self.uploads[upload_id] = {"key": key, "parts": {}}
        return upload_id

    def upload_part(self, key, upload_id, part_number, data):
        if self.fail_next > 0:
            self.fail_next -= 1
            raise StorageTimeoutError("fake timeout")
        self.uploads[upload_id]["parts"][part_number] = f"etag-{part_number}"
        return f"etag-{part_number}"

    def list_parts(self, key, upload_id):
        return dict(self.uploads[upload_id]["parts"])

    def complete_multipart_upload(self, key, upload_id, parts):
        assert len(parts) > 0
        return {"key": key, "etag": "final-etag", "location": f"https://fake/{key}"}

    def abort_multipart_upload(self, key, upload_id):
        self.uploads.pop(upload_id, None)


PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}{(' - ' + detail) if detail and not condition else ''}")
    if condition:
        PASSED += 1
    else:
        sys.exit(1)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cf_storage_test_"))
    key_file = tmp / ".storage_secret"
    configs_file = tmp / "storage_configs.json"
    uploads_dir = tmp / "uploads"

    # ── 1. 脱敏与 redact ────────────────────────────────────────────────────
    check("mask_secret 保留首尾 4 位", mask_secret("R8oGWJprgmvXXeMI5zr0") == "R8oG****5zr0")
    check("mask_secret 短值全打星", mask_secret("abcd") == "****")
    check("redact 打码 secret= 明文", "SKVALUE" not in redact("boom secret=SKVALUE x=1"))

    # ── 2. 加密配置存储：创建 / 脱敏 / 解密往返 ──────────────────────────────
    store = StorageConfigStore(path=str(configs_file), key_file=str(key_file))
    created = store.create({
        "name": "七牛测试", "provider": "kodo", "access_key": "AK1234567890abcdef",
        "secret_key": "SK0987654321fedcba", "region": "cn-east-1", "bucket": "creatforge",
    })
    check("创建返回脱敏视图", created["access_key"] == "AK12****cdef"
          and "****" in created["secret_key"])
    raw = json.loads(configs_file.read_text(encoding="utf-8"))
    row = raw["configs"][0]
    check("落盘密文不含明文 AK", "AK1234567890abcdef" not in configs_file.read_text(encoding="utf-8"))
    check("落盘密文字段是 Fernet token", row["secret_key"].startswith("gAAA") or len(row["secret_key"]) > 50)
    decrypted = store.get(created["id"])
    check("解密还原明文凭证", decrypted.access_key == "AK1234567890abcdef"
          and decrypted.secret_key == "SK0987654321fedcba")
    check("首条配置自动成为默认", store.get_default().id == created["id"])

    # ── 3. 编辑（敏感字段缺省保持原值）+ 默认切换 + 删除 ────────────────────
    second = store.create({
        "name": "OSS 测试", "provider": "oss", "access_key": "LTAI12345678",
        "secret_key": "osssecret0123456", "region": "cn-hangzhou", "bucket": "cf-bucket",
    })
    updated = store.update(created["id"], {"region": "cn-north-1"})  # 不带凭证
    check("编辑不动凭证", store.get(created["id"]).secret_key == "SK0987654321fedcba")
    check("编辑更新非敏感字段", updated["region"] == "cn-north-1")
    store.set_default(second["id"])
    check("默认切换生效", store.get_default().id == second["id"])
    store.delete(second["id"])
    check("删除后默认回落", store.get_default().id == created["id"])
    try:
        store.delete("no-such-id")
        check("删除不存在的配置报错", False)
    except StorageConfigError:
        check("删除不存在的配置报错", True)

    # ── 4. 端点解析 ─────────────────────────────────────────────────────────
    check("七牛 S3 端点", resolve_endpoint(StorageConfig(
        id="x", name="x", provider="kodo", region="cn-east-1", bucket="b"))
        == "https://s3.cn-east-1.qiniucs.com")
    check("腾讯 COS 端点", resolve_endpoint(StorageConfig(
        id="x", name="x", provider="cos", region="ap-shanghai", bucket="b"))
        == "https://cos.ap-shanghai.myqcloud.com")
    check("自定义 Endpoint 优先", resolve_endpoint(StorageConfig(
        id="x", name="x", provider="oss", region="cn-hangzhou", bucket="b",
        endpoint="https://my-proxy.example.com/")) == "https://my-proxy.example.com")

    # ── 5. 分片上传状态机 ───────────────────────────────────────────────────
    fake = FakeProvider()
    manager = MultipartManager(lambda config_id: fake, state_dir=str(uploads_dir))

    total_size, part_size = 20 * 1024 * 1024, 8 * 1024 * 1024  # 20MB → 3 片
    session = manager.start("cfg-1", "assets/big.zip", total_size, part_size=part_size)
    check("分片数正确", session["total_parts"] == 3 and session["missing_parts"] == [1, 2, 3])

    # 第 1 片：前两次失败一次成功（测重试）
    fake.fail_next = 1
    view = manager.upload_part(session["session_id"], 1, b"x" * part_size, attempts=3, timeout=5)
    check("失败重试后成功", 1 in view["uploaded_parts"] and view["progress"] > 0)

    # 模拟"本地状态丢失"：远端已传但状态文件没记 → resume 对账认账
    state_path = uploads_dir / f"{session['session_id']}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["parts"] = {}
    state_path.write_text(json.dumps(state), encoding="utf-8")
    resumed = manager.resume(session["session_id"])
    check("断点续传对账恢复远端分片", 1 in resumed["uploaded_parts"])

    # 分片大小校验与越界
    try:
        manager.upload_part(session["session_id"], 2, b"short")
        check("分片大小校验", False)
    except Exception as exc:
        check("分片大小校验", "大小不符" in str(exc))
    try:
        manager.upload_part(session["session_id"], 9, b"x" * part_size)
        check("分片号越界校验", False)
    except Exception as exc:
        check("分片号越界校验", "越界" in str(exc))

    # 完成前置校验：缺片不允许 complete
    try:
        manager.complete(session["session_id"])
        check("缺片禁止完成", False)
    except Exception as exc:
        check("缺片禁止完成", "分片未上传" in str(exc))

    manager.upload_part(session["session_id"], 2, b"x" * part_size)
    manager.upload_part(session["session_id"], 3, b"x" * (total_size - 2 * part_size))
    done = manager.complete(session["session_id"])
    check("全部分片后完成", done["status"] == "completed" and done["progress"] == 1.0)

    # 会话视图不含凭证字段
    check("会话视图无凭证字段",
          not any(k in json.dumps(manager.list_sessions()) for k in ("secret", "password")))

    print(f"\n{PASSED} 项全部通过（离线自测；连通性请用界面「测试连接」）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
