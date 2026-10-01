"""视频生产管线模块衔接契约测试（离线、零额度、无网络）。

对应视频生产模块优化的「模块衔接强化」要求：

  * 边界异常：空 / 截断 / 垃圾视频数据 → 立即给可读错误，而非解析异常风暴
  * 轮询契约：404/401 立即失败且错误分类正确（401→auth 自动换 Key，404→fatal）
  * meta 契约：落盘产物字段齐全（前端/试玩舞台/资产包导出依赖的字段集合）
  * 高并发压力：6 线程并行抽帧+合成互不干扰、结果可区分
  * 长时间稳定（浸泡）：30 轮顺序管线循环，时间有界、临时文件零残留

Run: python tests/test_video_pipeline.py
"""

import os
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))
    print(
        f"[{'PASS' if condition else 'FAIL'}] {name}"
        + (f" -- {detail}" if detail and not condition else "")
    )


def _synth_video_bytes(total=96, side=192, static_head=10):
    """合成 i2v 形态测试视频：静态开头 + 方块位移起伏。"""
    import numpy as np

    import imageio.v2 as imageio

    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    writer = imageio.get_writer(path, fps=24)
    for i in range(total):
        frame = np.full((side, side, 3), 235, dtype=np.uint8)
        if i >= static_head:
            t = (i - static_head) / max(1, total - static_head - 1)
            x = int(20 + t * (side - 120))
            y = int(side * 0.4 + (10 if (i // 5) % 2 else -10))
            frame[y : y + 50, x : x + 50] = (40, 60, 120)
        writer.append_data(frame)
    writer.close()
    with open(path, "rb") as handle:
        data = handle.read()
    os.remove(path)
    return data


def main() -> int:
    from artgen import compose_animation

    from studio.backend.animation_service.service import AnimationService
    from studio.backend.model_service import service as msvc

    tmpdir = tempfile.mkdtemp(prefix="cf_vidpipe_")
    service = AnimationService(tmpdir)
    video = _synth_video_bytes()

    # ── 1) 边界异常：脏输入立即干净报错 ──────────────────────────────────
    dirty_inputs = (
        ("empty", b""),
        ("truncated", video[:400]),
        ("garbage-4kb", os.urandom(4096)),
    )
    for name, payload in dirty_inputs:
        try:
            service._slice_video(payload, b"", 12, 1.0, 192, min_count=8)
            check(f"boundary {name}: rejected with clean error", False, "no error raised")
        except RuntimeError as exc:
            message = str(exc)
            ok = any(
                marker in message
                for marker in ("损坏", "无法解码", "过短", "有效帧不足")
            )
            check(f"boundary {name}: rejected with clean error", ok, message[:90])
        except Exception as exc:  # noqa: BLE001 - 非预期异常类型即失败
            check(f"boundary {name}: rejected with clean error", False, repr(exc)[:110])

    # ── 2) 轮询契约：4xx 快速失败 + 分类正确（mock httpx.get，无网络）────
    class _FakeResponse:
        def __init__(self, status):
            self.status_code = status

    original_get = msvc.httpx.get
    try:
        msvc.httpx.get = lambda *a, **k: _FakeResponse(401)
        try:
            msvc.poll_video_task("k", "task-401", 3)
            check("poll 401: fast-fail", False, "no error")
        except RuntimeError as exc:
            check(
                "poll 401: fast-fail + classified auth",
                "unauthorized" in str(exc) and msvc.classify_error(exc) == "auth",
                str(exc)[:90],
            )
        msvc.httpx.get = lambda *a, **k: _FakeResponse(404)
        try:
            msvc.poll_dashscope_task("k", "task-404", 3)
            check("poll 404: fast-fail", False, "no error")
        except RuntimeError as exc:
            check(
                "poll 404: fast-fail + classified fatal",
                "not found" in str(exc) and msvc.classify_error(exc) == "fatal",
                str(exc)[:90],
            )
    finally:
        msvc.httpx.get = original_get

    # ── 3) meta 契约：_persist 产物字段集合（下游消费者的依赖面）─────────
    frames = service._slice_video(video, b"", 12, 1.0, 192, min_count=12)
    result = compose_animation(frames_rgba=frames, fps=12, size=192)
    meta = service._persist(result, "contract01", "video")
    required = (
        "id",
        "source",
        "action",
        "fps",
        "duration",
        "frame_count",
        "frames",
        "frame_urls",
        "urls",
        "created_at",
    )
    missing = [key for key in required if key not in meta]
    check("persist meta: required fields present", not missing, str(missing))
    check("persist meta: urls triple", set(meta["urls"]) >= {"gif", "sheet", "thumb"})
    check(
        "persist meta: files on disk",
        all(
            os.path.isfile(os.path.join(tmpdir, os.path.basename(url)))
            for url in meta["frame_urls"][:3]
        ),
    )

    # ── 4) 高并发压力：6 线程并行抽帧+合成 ───────────────────────────────
    from concurrent.futures import ThreadPoolExecutor

    videos = [_synth_video_bytes(static_head=8 + i) for i in range(6)]

    def _one(index):
        sliced = service._slice_video(videos[index], b"", 12, 1.0, 192, min_count=12)
        composed = compose_animation(frames_rgba=sliced, fps=12, size=192)
        return len(sliced), len(composed["gif"])

    started = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(_one, range(6)))
    check(
        "concurrent x6: all succeed with valid output",
        all(n >= 12 and g > 1000 for n, g in outcomes),
        str(outcomes),
    )
    check(
        "concurrent x6: results distinguishable",
        len({g for _, g in outcomes}) >= 5,
        str([g for _, g in outcomes]),
    )
    check("concurrent x6: bounded wall time (<120s)", time.time() - started < 120)

    # ── 5) 浸泡：30 轮顺序管线循环 ───────────────────────────────────────
    started = time.time()
    ok_cycles = 0
    for _ in range(30):
        sliced = service._slice_video(video, b"", 12, 1.0, 192, min_count=12)
        composed = compose_animation(frames_rgba=sliced, fps=12, size=192)
        if len(sliced) >= 12 and len(composed["gif"]) > 1000:
            ok_cycles += 1
    elapsed = time.time() - started
    check("soak 30 cycles: all succeed", ok_cycles == 30, f"{ok_cycles}/30")
    check("soak 30 cycles: bounded time (<90s)", elapsed < 90, f"{elapsed:.1f}s")
    # 残留收割是异步的（Windows ffmpeg 退出竞态 → 后台线程重试删除），
    # 轮询等待收割完成而非断言瞬时干净
    leftovers = [name for name in os.listdir(tmpdir) if name.startswith("tmp_")]
    deadline = time.time() + 10
    while leftovers and time.time() < deadline:
        time.sleep(0.3)
        leftovers = [name for name in os.listdir(tmpdir) if name.startswith("tmp_")]
    check("soak: zero tmp video leftovers (reaper within 10s)", not leftovers, str(leftovers[:5]))

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
