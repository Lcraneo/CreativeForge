"""大文件分片上传管理器：分片 / 断点续传 / 失败重试 / 超时控制。

复用参考项目（Windup）沉淀的工程思路：幂等重试（同 key 同分片号重传无副作用）、
状态落盘（进程重启可恢复）、超时预算显式化。分片对账逻辑为本模块自建
（参考项目没有分片能力）：

- 每个 upload session 一份状态文件 ``data/uploads/<session_id>.json``；
- 断点续传：本地状态与远端 ``list_parts`` 对账 —— 远端已传但本地没记的分片
  直接认账；本地已记的以远端为准（upload_part 幂等，重传即覆盖）；
- 失败重试：分片级指数退避（默认 3 次），鉴权/配置类错误不重试；
- 超时控制：单分片调用超时 + 整体重试 deadline 双层。
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from collections.abc import Callable
from typing import Protocol

from .interface import (
    StorageAuthError,
    StorageConfigError,
    StorageError,
    StorageNotFoundError,
    StorageTimeoutError,
    StorageTransferError,
    redact,
)

__all__ = ["MultipartCapable", "MultipartManager", "DEFAULT_PART_SIZE", "MIN_PART_SIZE"]

DEFAULT_PART_SIZE = 8 * 1024 * 1024  # 8MB
MIN_PART_SIZE = 5 * 1024 * 1024  # S3 MPU 协议最小分片（末片除外）
MAX_PART_NUMBER = 10000
UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "uploads")


class MultipartCapable(Protocol):
    """分片扩展端口（S3CompatProvider 实现；测试可注入假实现）。"""

    def create_multipart_upload(
        self, key: str, *, content_type: str = "application/octet-stream"
    ) -> str: ...

    def upload_part(self, key: str, upload_id: str, part_number: int, data: bytes) -> str: ...

    def list_parts(self, key: str, upload_id: str) -> dict[int, str]: ...

    def complete_multipart_upload(
        self, key: str, upload_id: str, parts: list[tuple[int, str]]
    ) -> dict: ...

    def abort_multipart_upload(self, key: str, upload_id: str) -> None: ...


def _retry(
    call: Callable[[], object],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    deadline: float | None = None,
    action: str = "",
) -> object:
    """分片级重试：可重试错误退避后重试，配置/鉴权错误立即抛。"""
    last: Exception | None = None
    for attempt in range(max(1, attempts)):
        if deadline is not None and time.time() >= deadline:
            raise StorageTimeoutError(redact(f"{action}: 整体重试预算耗尽（已试 {attempt} 次）"))
        try:
            return call()
        except (StorageAuthError, StorageConfigError, StorageNotFoundError):
            raise  # 重试没有意义，直接暴露根因
        except (StorageTimeoutError, StorageTransferError, StorageError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(base_delay * (2**attempt))
    assert last is not None
    raise last


class MultipartManager:
    """分片会话管理器。provider_factory 按需重建 provider（支持重启恢复）。"""

    def __init__(
        self, provider_factory: Callable[[str], MultipartCapable], state_dir: str | None = None
    ):
        self._factory = provider_factory
        self._dir = os.path.abspath(state_dir or UPLOADS_DIR)
        self._lock = threading.Lock()
        os.makedirs(self._dir, exist_ok=True)

    # ── 状态文件 ────────────────────────────────────────────────────────────

    def _path(self, session_id: str) -> str:
        return os.path.join(self._dir, f"{session_id}.json")

    def _load(self, session_id: str) -> dict:
        path = self._path(session_id)
        if not os.path.isfile(path):
            raise StorageNotFoundError(f"上传会话不存在：{session_id}")
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        if state.get("status") == "aborted":
            raise StorageTransferError(f"会话已取消：{session_id}")
        if state.get("status") == "completed":
            raise StorageTransferError(f"会话已完成：{session_id}")
        return state

    def _save(self, state: dict) -> None:
        tmp = self._path(state["session_id"]) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False)
        os.replace(tmp, self._path(state["session_id"]))

    def _provider(self, state: dict) -> MultipartCapable:
        return self._factory(state["config_id"])

    # ── 对外 API ────────────────────────────────────────────────────────────

    def start(
        self,
        config_id: str,
        key: str,
        total_size: int,
        *,
        part_size: int = DEFAULT_PART_SIZE,
        content_type: str = "application/octet-stream",
    ) -> dict:
        if total_size <= 0:
            raise StorageError("total_size 必须为正")
        if part_size < MIN_PART_SIZE:
            raise StorageError(f"分片不能小于 {MIN_PART_SIZE} 字节（S3 MPU 协议约束）")
        total_parts = math.ceil(total_size / part_size)
        if total_parts > MAX_PART_NUMBER:
            raise StorageError(f"分片数超限：{total_parts} > {MAX_PART_NUMBER}，请增大分片尺寸")
        provider = self._factory(config_id)
        upload_id = str(
            _retry(
                lambda: provider.create_multipart_upload(key, content_type=content_type),
                action=f"create_multipart_upload {key}",
            )
        )
        state = {
            "session_id": uuid.uuid4().hex[:16],
            "config_id": config_id,
            "key": key,
            "content_type": content_type,
            "total_size": total_size,
            "part_size": part_size,
            "total_parts": total_parts,
            "upload_id": upload_id,
            "parts": {},  # {part_number(str): etag}
            "status": "uploading",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            self._save(state)
        return self._view(state)

    def upload_part(
        self,
        session_id: str,
        part_number: int,
        data: bytes,
        *,
        timeout: float = 300.0,
        attempts: int = 3,
    ) -> dict:
        deadline = time.time() + timeout
        with self._lock:
            state = self._load(session_id)
        if not 1 <= part_number <= state["total_parts"]:
            raise StorageError(f"分片号越界：{part_number}（共 {state['total_parts']} 片）")
        if part_number < state["total_parts"]:
            expected = state["part_size"]
        else:
            expected = state["total_size"] - (part_number - 1) * state["part_size"]
        if len(data) != expected:
            raise StorageError(f"分片 {part_number} 大小不符：收到 {len(data)}，应为 {expected}")
        provider = self._provider(state)
        etag = str(
            _retry(
                lambda: provider.upload_part(state["key"], state["upload_id"], part_number, data),
                attempts=attempts,
                deadline=deadline,
                action=f"upload_part {part_number}/{state['total_parts']}",
            )
        )
        with self._lock:
            state = self._load(session_id)
            state["parts"][str(part_number)] = etag
            state["updated_at"] = time.time()
            self._save(state)
        return self._view(state)

    def resume(self, session_id: str) -> dict:
        """断点续传：与远端 list_parts 对账，返回仍缺的分片号。"""
        with self._lock:
            state = self._load(session_id)
        provider = self._provider(state)
        remote = _retry(
            lambda: provider.list_parts(state["key"], state["upload_id"]), action="list_parts"
        )
        with self._lock:
            state = self._load(session_id)
            state["parts"] = {str(n): str(etag) for n, etag in remote.items()}
            state["updated_at"] = time.time()
            self._save(state)
        return self._view(state)

    def complete(self, session_id: str) -> dict:
        with self._lock:
            state = self._load(session_id)
        missing = self._missing(state)
        if missing:
            raise StorageTransferError(
                f"还有 {len(missing)} 个分片未上传（如 {missing[:5]}），先续传再完成"
            )
        provider = self._provider(state)
        parts = sorted((int(n), etag) for n, etag in state["parts"].items())
        result = _retry(
            lambda: provider.complete_multipart_upload(state["key"], state["upload_id"], parts),
            action="complete_multipart_upload",
        )
        with self._lock:
            state = self._load(session_id)
            state["status"] = "completed"
            state["result"] = result if isinstance(result, dict) else {"done": True}
            state["updated_at"] = time.time()
            self._save(state)
        return self._view(state)

    def abort(self, session_id: str) -> dict:
        with self._lock:
            state = self._load(session_id)
        provider = self._provider(state)
        _retry(
            lambda: provider.abort_multipart_upload(state["key"], state["upload_id"]),
            attempts=2,
            action="abort_multipart_upload",
        )
        with self._lock:
            state["status"] = "aborted"
            state["updated_at"] = time.time()
            self._save(state)
        return self._view(state)

    def status(self, session_id: str) -> dict:
        with self._lock:
            return self._view(self._load(session_id))

    def list_sessions(self) -> list[dict]:
        sessions = []
        for name in sorted(os.listdir(self._dir)):
            if not name.endswith(".json") or name.endswith(".tmp.json"):
                continue
            try:
                with open(os.path.join(self._dir, name), "r", encoding="utf-8") as handle:
                    sessions.append(self._view(json.load(handle)))
            except (ValueError, OSError):
                continue
        return sessions

    # ── 内部 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _missing(state: dict) -> list[int]:
        done = {int(n) for n in state.get("parts", {})}
        return [n for n in range(1, state["total_parts"] + 1) if n not in done]

    def _view(self, state: dict) -> dict:
        """会话的对外视图（不含凭证；config_id 只给脱敏 id）。"""
        done = {int(n) for n in state.get("parts", {})}
        bytes_done = len(done) * state["part_size"]
        return {
            "session_id": state["session_id"],
            "config_id": state["config_id"],
            "key": state["key"],
            "total_size": state["total_size"],
            "part_size": state["part_size"],
            "total_parts": state["total_parts"],
            "uploaded_parts": sorted(done),
            "missing_parts": self._missing(state),
            "bytes_done": min(bytes_done, state["total_size"]),
            "progress": round(len(done) / max(state["total_parts"], 1), 4),
            "status": state["status"],
            "created_at": state["created_at"],
            "updated_at": state["updated_at"],
        }
