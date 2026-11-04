"""试玩条带打包：AI 视频帧 → 透明横条 PNG。

为什么单独成模块：
  - 抠图 + 打包在低配容器（0.1~0.5 vCPU）上很贵（32 帧 384px
    实测要几十秒），不能放在 ``GET /api/playtest/previews`` 的请求线程里；
  - 生成完成时后台预热一次，之后预览只读缓存文件（毫秒级）；
  - 缓存文件由 artifact_store 后台同步到对象存储，容器重启后按需回源。

打包口径（与历史条带一致）：
  - 帧数超过 ``MAX_FRAMES`` 时均匀抽样，控制解码/抠图开销；
  - 任一帧抠图失败则整条作废，由调用方回退程序化/骨骼条带；
  - 帧宽封顶 288px（舞台展示高度 ~216px），帧底对齐（脚底贴地）。
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

MAX_FRAMES = 16
CACHE_VERSION = "matte-v5"
FRAME_WIDTH_CAP = 288
# 旧版本缓存：纯白底时代产物，允许直接复用，避免升级后整套重抠
LEGACY_VERSIONS = ("matte-v4", "matte-v3")

_BUILDING: set[str] = set()
_BUILD_LOCK = threading.Lock()
# 串行打包：批量补齐一次会同时完成多条动作，并行抠图在 0.5 vCPU 上
# 只会互相拖慢、还可能挤占下一次视频生成的 CPU
_BUILD_SEMAPHORE = threading.Semaphore(1)


def _safe_label(value: str) -> str:
    return re.sub(r"[^\w-]+", "_", str(value), flags=re.UNICODE)


def _digest(version: str, animation_id: str, frame_count: int) -> str:
    return hashlib.sha1(
        "ai|{}|{}|{}".format(version, animation_id, frame_count).encode()
    ).hexdigest()[:10]


def _cache_name(version: str, action: str, animation_id: str, frame_count: int) -> str:
    return "play_ai_{}_{}_{}.png".format(
        _safe_label(action), _digest(version, animation_id, frame_count), version
    )


def sample_indexes(frame_count: int, limit: int = MAX_FRAMES) -> list[int]:
    """均匀抽样帧序号；不足 limit 时全取。"""
    if frame_count <= 0:
        return []
    if frame_count <= limit:
        return list(range(frame_count))
    # 覆盖首尾，动作循环的过渡帧不丢
    return sorted({round(index * (frame_count - 1) / (limit - 1)) for index in range(limit)})


def cache_names(meta: dict) -> list[tuple[str, int]]:
    """候选缓存文件 (文件名, 帧数)，新版本优先、旧版本按全量帧数。"""
    frame_urls = meta.get("frame_urls") or []
    total = len(frame_urls)
    if total < 4:
        return []
    action = meta.get("requested_action") or meta.get("action") or "action"
    animation_id = str(meta.get("id") or "")
    sampled = len(sample_indexes(total))
    candidates = [(CACHE_VERSION, sampled), *((version, total) for version in LEGACY_VERSIONS)]
    return [(_cache_name(version, action, animation_id, count), count) for version, count in candidates]


def cached_strip_path(cache_dir: str, meta: dict) -> tuple[str, int] | None:
    """返回 (缓存文件路径, 实际帧数)；只读磁盘，不触发打包。"""
    for name, count in cache_names(meta):
        path = os.path.join(cache_dir, name)
        if os.path.isfile(path):
            return path, count
    return None


def _resolve_frame(animation_dir: str, url: str, ensure_frame) -> str | None:
    name = os.path.basename(url)
    path = os.path.join(animation_dir, name)
    if os.path.isfile(path):
        return path
    if ensure_frame is not None:
        try:
            ensured = ensure_frame(name)
        except Exception:  # noqa: BLE001 - 回源失败按缺帧处理
            ensured = None
        if ensured and os.path.isfile(ensured):
            return ensured
    try:
        from studio.backend import artifact_store

        resolved = artifact_store.ensure_local("data/animation/" + name)
        if resolved and os.path.isfile(resolved):
            return resolved
    except Exception:  # noqa: BLE001
        pass
    return None


def build_strip(
    meta: dict,
    animation_dir: str,
    cache_dir: str,
    ensure_frame=None,
) -> tuple[str, int] | None:
    """构建并落盘一条 AI 透明条带；返回 (路径, 帧数)。任何失败返回 None。"""
    from PIL import Image as PILImage

    from artgen.sourceanim import cutout_white_background

    frame_urls = meta.get("frame_urls") or []
    total = len(frame_urls)
    if total < 4:
        return None
    indexes = sample_indexes(total)
    action = meta.get("requested_action") or meta.get("action") or "action"
    animation_id = str(meta.get("id") or "")
    out_name = _cache_name(CACHE_VERSION, action, animation_id, len(indexes))
    out_path = os.path.join(cache_dir, out_name)
    if os.path.isfile(out_path):
        return out_path, len(indexes)

    os.makedirs(cache_dir, exist_ok=True)

    # 1) 并行回源/找本地帧（对象存储冷启动时这里是大头）
    with ThreadPoolExecutor(max_workers=min(8, len(indexes))) as pool:
        paths = list(
            pool.map(
                lambda index: _resolve_frame(animation_dir, frame_urls[index], ensure_frame),
                indexes,
            )
        )
    samples = [path for path in paths if path]
    if len(samples) < 4:
        return None

    # 2) 并行抠图：PIL/numpy 多数算子会释放 GIL，4 线程在白底洪泛上有明显收益
    def _cutout(path: str):
        try:
            with PILImage.open(path) as handle:
                return cutout_white_background(handle)
        except Exception:  # noqa: BLE001 - 单帧失败 → 整条作废
            return None

    with ThreadPoolExecutor(max_workers=min(4, len(samples))) as pool:
        cut = list(pool.map(_cutout, samples))
    if any(frame is None for frame in cut):
        return None
    images = [frame for frame in cut if frame is not None]

    # 3) 等比缩放 + 底部对齐拼条（帧宽封顶，控内存）
    if images[0].width > FRAME_WIDTH_CAP:
        images = [
            image.convert("RGBa")
            .resize(
                (
                    FRAME_WIDTH_CAP,
                    max(1, int(image.height * FRAME_WIDTH_CAP / image.width)),
                ),
                PILImage.LANCZOS,
            )
            .convert("RGBA")
            for image in images
        ]
    frame_w = max(image.width for image in images)
    frame_h = max(image.height for image in images)
    sheet = PILImage.new("RGBA", (frame_w * len(images), frame_h), (0, 0, 0, 0))
    for index, image in enumerate(images):
        sheet.paste(
            image,
            (index * frame_w + (frame_w - image.width) // 2, frame_h - image.height),
        )
    # 原子落盘：避免后台同步/并发请求读到半截文件
    tmp_path = out_path + ".tmp"
    sheet.save(tmp_path, "PNG")
    os.replace(tmp_path, out_path)
    return out_path, len(images)


def schedule_strip(
    meta: dict,
    animation_dir: str,
    cache_dir: str,
    ensure_frame=None,
) -> bool:
    """后台预热一条条带（同一缓存文件去重）。返回是否真正排入线程。"""
    frame_urls = meta.get("frame_urls") or []
    total = len(frame_urls)
    if total < 4:
        return False
    action = meta.get("requested_action") or meta.get("action") or "action"
    name = _cache_name(
        CACHE_VERSION,
        action,
        str(meta.get("id") or ""),
        len(sample_indexes(total)),
    )
    target = os.path.join(cache_dir, name)
    if os.path.isfile(target):
        return False
    with _BUILD_LOCK:
        if name in _BUILDING:
            return False
        _BUILDING.add(name)

    def _run() -> None:
        try:
            with _BUILD_SEMAPHORE:
                build_strip(meta, animation_dir, cache_dir, ensure_frame=ensure_frame)
        except Exception:  # noqa: BLE001 - 后台预热失败不影响主链
            pass
        finally:
            with _BUILD_LOCK:
                _BUILDING.discard(name)

    threading.Thread(target=_run, name="cf-play-strip-{}".format(name), daemon=True).start()
    return True
