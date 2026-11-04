"""产物与状态的对象存储同步层（本地优先，云端兜底）。

托管环境（Render 等）没有持久盘：容器每次重新部署，``generated/``、
``data/``、``history.json`` 全部清空——资产图片裂图、历史记录消失。

本模块把对象存储当作「冷备份 + 数据源」：

  - **启动回填**：先拉取 ``artifacts/_manifest.json``，再按清单把状态文件
    （``history.json``、``*.json`` 索引）恢复到本地，供 AgentRuntime 正常装载；
  - **后台增量上传**：扫描产物目录，把新产生的原画 / 动画帧 / 场景图 / 索引
    同步到对象存储（按 mtime+size 判重，重启不重传）；
  - **按需回源**：读取接口发现本地缺文件时，从对象存储下载并写回本地缓存，
    对外 URL 保持 ``/api/generated/...`` 不变，前端与历史元数据无需迁移。

凭证与配置完全复用 ``storage_service``（加密配置或 QINIU_* / STORAGE_* 环境
变量）；未配置对象存储时本模块全部为 no-op，行为与改造前一致。
"""

from __future__ import annotations

import json
import os
import threading
import time

__all__ = [
    "configured",
    "rel_for",
    "abs_for",
    "ensure_local",
    "read_bytes",
    "restore_state",
    "restore_prefix",
    "start_worker",
    "sync_now",
]

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR = os.path.join(BACKEND_DIR, "generated")
DATA_DIR = os.path.join(BACKEND_DIR, "data")
HISTORY_DIR = os.path.join(BACKEND_DIR, "history_service")

# 本地目录 → 对象存储 key 前缀（key 统一放在 artifacts/ 下，避免与用户
# 自己在同一桶里放的其它对象混淆）。用函数而非模块常量，测试可替换目录。

_KEY_PREFIX = "artifacts/"
_MANIFEST_KEY = _KEY_PREFIX + "_manifest.json"

# 绝不外传：加密密钥文件、加密后的云存储配置（一旦泄露等于凭证泄露）
_SKIP_NAMES = frozenset(
    {".storage_secret", "storage_configs.json", ".artifact_index.json"}
)
_SKIP_SUFFIXES = (".tmp", ".part", ".py", ".pyc")

_STATE_SUFFIXES = (".json",)

_MAX_FILE_MB = 64
_TIMEOUT = 15
_SCAN_INTERVAL = 8.0
_UPLOADS_PER_CYCLE = 60
_UPLOAD_SETTLE_SECONDS = 2.0  # 刚写完的文件等下一轮再传，避免半截文件
_PROVIDER_TTL = 60.0

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".json": "application/json",
    ".zip": "application/zip",
    ".glb": "model/gltf-binary",
}

_PROVIDER_LOCK = threading.Lock()
_provider_cache: tuple[float, object] = (0.0, None)

_INDEX_LOCK = threading.Lock()
_index: dict[str, list] = {}
_index_dirty = False
_manifest: set[str] = set()
_manifest_dirty = False

_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()
_RUNNING = True


# ── 路径映射 ────────────────────────────────────────────────────────────────


def _norm(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def _roots() -> tuple:
    """当前目录映射（每次读取模块全局，便于测试替换与运行时改路径）。"""
    return (
        (GENERATED_DIR, "generated"),
        (DATA_DIR, "data"),
        (HISTORY_DIR, "history"),
    )


def _index_path() -> str:
    return os.path.join(DATA_DIR, ".artifact_index.json")


def rel_for(abs_path: str) -> str | None:
    """绝对路径 → 相对标识（``generated/x.png`` / ``data/...`` / ``history/...``）。"""
    target = _norm(abs_path)
    for root, prefix in _roots():
        base = _norm(root)
        if target.startswith(base + os.sep):
            return prefix + "/" + target[len(base) + 1 :].replace(os.sep, "/")
    return None


def abs_for(rel: str) -> str | None:
    """相对标识 → 本地绝对路径（越界一律拒绝）。"""
    if not rel or ".." in rel:
        return None
    prefix, _, tail = rel.partition("/")
    if not tail:
        return None
    for root, name in _roots():
        if name != prefix:
            continue
        target = _norm(os.path.join(root, tail))
        base = _norm(root)
        if target.startswith(base + os.sep):
            return target
        return None
    return None


def _skip(name: str) -> bool:
    if name in _SKIP_NAMES:
        return True
    return any(name.endswith(suffix) for suffix in _SKIP_SUFFIXES)


def _storage_key(rel: str) -> str:
    return _KEY_PREFIX + rel


def _content_type(path: str) -> str:
    return _CONTENT_TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")


# ── provider 解析（未配置时全部 no-op） ─────────────────────────────────────


def _provider():
    """返回 (provider, config)；未配置对象存储时 (None, None)。带 60s 缓存。"""
    global _provider_cache
    now = time.time()
    with _PROVIDER_LOCK:
        stamp, cached = _provider_cache
        if now - stamp < _PROVIDER_TTL:
            return cached, None
    provider = None
    try:
        from studio.backend.storage_service import get_storage_manager
        from studio.backend.storage_service.providers import create_provider

        config = get_storage_manager().store.get_default()
        if config is not None:
            provider = create_provider(config, timeout=_TIMEOUT)
    except Exception:  # noqa: BLE001 - 配置缺失/依赖缺失都不该阻断主流程
        provider = None
    with _PROVIDER_LOCK:
        _provider_cache = (now, provider)
    return provider, None


def configured() -> bool:
    return _provider()[0] is not None


# ── 上传索引 ────────────────────────────────────────────────────────────────


def _load_index() -> None:
    global _index
    try:
        with open(_index_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            _index = {str(k): list(v) for k, v in data.items() if isinstance(v, list)}
    except (OSError, ValueError):
        _index = {}


def _flush_index() -> None:
    global _index_dirty
    with _INDEX_LOCK:
        if not _index_dirty:
            return
        if not configured():
            return
        payload = dict(_index)
        _index_dirty = False
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        target = _index_path()
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp, target)
    except OSError:
        pass


def _mark_synced(rel: str, abs_path: str) -> None:
    global _index_dirty
    try:
        stat = os.stat(abs_path)
    except OSError:
        return
    with _INDEX_LOCK:
        _index[rel] = [stat.st_mtime, stat.st_size]
        _index_dirty = True


def _needs_upload(rel: str, abs_path: str) -> bool:
    try:
        stat = os.stat(abs_path)
    except OSError:
        return False
    if stat.st_size <= 0 or stat.st_size > _MAX_FILE_MB * 1024 * 1024:
        return False
    if time.time() - stat.st_mtime < _UPLOAD_SETTLE_SECONDS:
        return False  # 可能仍在写入
    with _INDEX_LOCK:
        known = _index.get(rel)
    if not known or len(known) != 2:
        return True
    return int(known[1]) != stat.st_size or abs(float(known[0]) - stat.st_mtime) > 1e-6


# ── 上传 / 下载 ─────────────────────────────────────────────────────────────


def upload_file(abs_path: str, provider=None) -> bool:
    """把单个文件传到对象存储；失败返回 False（调用方下一轮重试）。"""
    provider = provider or _provider()[0]
    if provider is None:
        return False
    rel = rel_for(abs_path)
    if rel is None or _skip(os.path.basename(abs_path)):
        return False
    try:
        with open(abs_path, "rb") as handle:
            data = handle.read()
        provider.upload(data, _storage_key(rel), content_type=_content_type(abs_path))
    except Exception:  # noqa: BLE001 - 网络/凭证问题不阻断生成主流程
        return False
    _mark_synced(rel, abs_path)
    if os.path.basename(abs_path).endswith(_STATE_SUFFIXES):
        with _INDEX_LOCK:
            global _manifest_dirty
            if rel not in _manifest:
                _manifest.add(rel)
                _manifest_dirty = True
    return True


def _flush_manifest(provider) -> None:
    global _manifest_dirty
    with _INDEX_LOCK:
        if not _manifest_dirty or not _manifest:
            return
        payload = {"state_files": sorted(_manifest), "updated_at": time.time()}
        _manifest_dirty = False
    try:
        provider.upload(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            _MANIFEST_KEY,
            content_type="application/json",
        )
    except Exception:  # noqa: BLE001
        with _INDEX_LOCK:
            _manifest_dirty = True


def _download_to(provider, rel: str) -> str | None:
    """从对象存储取回单个文件并原子写入本地，返回本地路径。"""
    path = abs_for(rel)
    if path is None:
        return None
    try:
        data = provider.download(_storage_key(rel))
    except Exception:  # noqa: BLE001 - 对象不存在/网络问题时返回 None
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except OSError:
        return None
    _mark_synced(rel, path)
    return path


def ensure_local(rel: str) -> str | None:
    """本地缺文件时按需回源；已有文件直接返回路径。"""
    path = abs_for(rel)
    if path is None:
        return None
    if os.path.isfile(path):
        return path
    provider = _provider()[0]
    if provider is None:
        return None
    return _download_to(provider, rel)


def read_bytes(rel: str) -> bytes | None:
    """读取产物字节：本地优先，缺失则回源。"""
    path = ensure_local(rel)
    if path is None:
        return None
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


# ── 启动回填 ────────────────────────────────────────────────────────────────


def _load_manifest(provider) -> set[str]:
    """读取云端清单（状态文件列表）。清单不存在时返回空集合。"""
    try:
        payload = json.loads(provider.download(_MANIFEST_KEY).decode("utf-8"))
    except Exception:  # noqa: BLE001 - 首次部署时清单还不存在
        return set()
    files = payload.get("state_files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        return set()
    return {item for item in files if isinstance(item, str)}


def _restore_remote(provider, rels: list[str], deadline: float) -> int:
    """并行回填状态文件：单个下载 0.2~0.5s 时串行会卡在 deadline，
    真实故障现场就是历史库排在字母序最后、40s 内没轮到而被丢弃。"""
    from concurrent.futures import ThreadPoolExecutor, wait

    pending = []
    for rel in rels:
        path = abs_for(rel)
        if path is not None and not os.path.isfile(path):
            pending.append(rel)
    if not pending:
        return 0

    def _restore_one(rel: str) -> int:
        path = abs_for(rel)
        if path is None or os.path.isfile(path):
            return 0
        return 1 if _download_to(provider, rel) else 0

    executor = ThreadPoolExecutor(max_workers=min(8, len(pending)))
    futures = [executor.submit(_restore_one, rel) for rel in pending]
    done, not_done = wait(futures, timeout=deadline)
    restored = 0
    for future in done:
        try:
            restored += int(future.result() or 0)
        except Exception:  # noqa: BLE001
            continue
    for future in not_done:
        future.cancel()
    executor.shutdown(wait=False, cancel_futures=True)
    return restored


def restore_state(deadline: float = 40.0) -> int:
    """把状态文件（history.json 与各类 *.json 索引）回填到本地。

    必须在 :class:`AgentRuntime` 构造之前调用——历史库在初始化时一次性载入
    内存，晚于构造的回填不会反映到运行时。
    """
    provider = _provider()[0]
    if provider is None:
        return 0
    remote_files = _load_manifest(provider)
    if not remote_files:
        return 0
    # 新容器的清单集合是空的：必须先并入云端清单，否则后台同步后续写的
    # 清单会只含新文件、把历史状态文件列表覆盖掉
    with _INDEX_LOCK:
        _manifest.update(remote_files)

    # 历史/场景/资产索引优先：串行时代的 40s deadline 刚好把它们饿死，
    # 重启后工作台“资产全没了、动作却还在”。
    def _priority(rel: str) -> int:
        if rel.startswith("history/"):
            return 0
        if rel.startswith("data/scenes/"):
            return 1
        if rel.startswith("data/assets/"):
            return 2
        if rel.startswith("data/animation/"):
            return 3
        return 4

    ordered = sorted(remote_files, key=lambda rel: (_priority(rel), rel))
    return _restore_remote(provider, ordered, deadline)


def restore_prefix(prefix: str, deadline: float = 20.0) -> int:
    """按前缀补齐云端状态文件（如 ``data/animation/`` 的动画 meta）。

    启动回填被 deadline 截断后，动画扫描会看不到历史 meta，误判“动作未
    生成”让用户重做并重复计费。扫描前调用本函数把该前缀补齐。
    """
    provider = _provider()[0]
    if provider is None:
        return 0
    with _INDEX_LOCK:
        remote = set(_manifest)
    if not remote:
        remote = _load_manifest(provider)
        with _INDEX_LOCK:
            _manifest.update(remote)
    rels = sorted(
        rel
        for rel in remote
        if rel.startswith(prefix) and rel.endswith(_STATE_SUFFIXES)
    )
    return _restore_remote(provider, rels, deadline)


# ── 后台增量同步 ────────────────────────────────────────────────────────────


def _scan_once(provider) -> int:
    uploaded = 0
    for root, _prefix in _roots():
        if uploaded >= _UPLOADS_PER_CYCLE:
            break
        base = _norm(root)
        if not os.path.isdir(base):
            continue
        for current, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if uploaded >= _UPLOADS_PER_CYCLE:
                    break
                if _skip(name):
                    continue
                abs_path = os.path.join(current, name)
                rel = rel_for(abs_path)
                if rel is None or not _needs_upload(rel, abs_path):
                    continue
                if upload_file(abs_path, provider):
                    uploaded += 1
    return uploaded


def sync_now() -> int:
    """立即全量扫描一次（运维/测试用）。"""
    provider = _provider()[0]
    if provider is None:
        return 0
    with _INDEX_LOCK:
        _manifest.update(_load_manifest(provider))
    total = 0
    while True:
        done = _scan_once(provider)
        total += done
        if done < _UPLOADS_PER_CYCLE:
            break
    _flush_manifest(provider)
    _flush_index()
    return total


def _worker_loop() -> None:
    global _RUNNING
    _load_index()
    provider = _provider()[0]
    if provider is not None:
        # 先并入云端清单：否则本进程只见过自己新传的状态文件，
        # 一旦落清单就会把历史列表覆盖掉
        with _INDEX_LOCK:
            _manifest.update(_load_manifest(provider))
    while _RUNNING:
        try:
            provider = _provider()[0]
            if provider is not None:
                _scan_once(provider)
                _flush_manifest(provider)
                _flush_index()
        except Exception:  # noqa: BLE001 - 后台线程不允许中断服务
            pass
        time.sleep(_SCAN_INTERVAL)


def start_worker() -> bool:
    """启动后台同步线程（幂等）。未配置对象存储时不启动。"""
    global _WORKER_STARTED
    if os.environ.get("CF_ARTIFACT_SYNC", "").strip().lower() in ("off", "0", "false"):
        return False
    if not configured():
        return False
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return True
        thread = threading.Thread(
            target=_worker_loop, name="artifact-sync", daemon=True
        )
        thread.start()
        _WORKER_STARTED = True
    return True
