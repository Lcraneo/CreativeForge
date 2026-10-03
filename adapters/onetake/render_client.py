"""render_client — third_party/onetake 渲染/验收管线的子进程封装。

调用纪律：vendored 脚本零改动，只经 CLI 标志与环境变量驱动；ffmpeg 用
imageio-ffmpeg 自带二进制（PATH 注入，不在机器级装 ffmpeg）。业务只经本模块
触达 third_party（boundaries 纪律）。
"""

import os
import subprocess
import sys
import threading

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ONETAKE_DIR = os.path.join(_REPO_ROOT, "third_party", "onetake")
SCRIPTS_DIR = os.path.join(ONETAKE_DIR, "scripts")

RENDER_TIMEOUT_S = 900.0
VERIFY_TIMEOUT_S = 300.0


class RenderEnvironmentError(RuntimeError):
    """渲染环境未就绪（playwright/ffmpeg），给出可执行的修复指引。"""


def playwright_available() -> bool:
    try:
        import importlib.util

        if importlib.util.find_spec("playwright") is None:
            return False
        # chromium 浏览器本体是否已安装（playwright 缓存目录探测，Windows/Linux/macOS）
        home = os.path.expanduser("~")
        for candidate in (
            os.path.join(home, "AppData", "Local", "ms-playwright"),
            os.path.join(home, ".cache", "ms-playwright"),
            os.path.join(home, "Library", "Caches", "ms-playwright"),
        ):
            if os.path.isdir(candidate) and any(
                name.startswith("chromium") for name in os.listdir(candidate)
            ):
                return True
        return False
    except Exception:  # noqa: BLE001 - 环境探测永不抛出
        return False


def ensure_environment() -> None:
    if not playwright_available():
        raise RenderEnvironmentError(
            "演示机未安装 playwright/chromium：先执行 "
            "`python -m pip install playwright` 与 `python -m playwright install chromium`"
        )
    ffmpeg, _ffprobe = _ff_binaries()
    if not ffmpeg:
        raise RenderEnvironmentError(
            "未找到 ffmpeg/static-ffmpeg：`python -m pip install static-ffmpeg`"
        )


def _ff_binaries() -> tuple[str | None, str | None]:
    """→ (ffmpeg, ffprobe) 绝对路径。static-ffmpeg 优先（含 ffprobe，oracle
    需要），imageio-ffmpeg 兜底（仅 ffmpeg）。"""

    try:
        from static_ffmpeg import run

        ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
        return ffmpeg, ffprobe
    except Exception:  # noqa: BLE001
        pass
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe(), None
    except Exception:  # noqa: BLE001
        return None, None


def _ffmpeg_dir() -> str | None:
    ffmpeg, _ffprobe = _ff_binaries()
    return os.path.dirname(ffmpeg) if ffmpeg else None


def _env() -> dict:
    env = os.environ.copy()
    ffmpeg_dir = _ffmpeg_dir()
    if ffmpeg_dir:
        env["PATH"] = ffmpeg_dir + os.pathsep + env.get("PATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _run(cmd: list[str], cwd: str, timeout: float, on_line=None) -> tuple[int, str]:
    """流式子进程（渲染进度可观测；deadline 到点杀进程树）。"""

    proc = subprocess.Popen(  # noqa: S603 - 固定参数列表，无外部输入拼接
        cmd,
        cwd=cwd,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    chunks: list[str] = []
    watcher = threading.Thread(
        target=_pump, args=(proc, chunks, on_line), name="cf-onetake-pump", daemon=True
    )
    watcher.start()
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("渲染超时（>{}s），已终止".format(int(timeout))) from None
    watcher.join(timeout=5.0)
    return code, "".join(chunks)


def _pump(proc, chunks, on_line):
    try:
        for line in proc.stdout or []:
            chunks.append(line)
            if on_line:
                try:
                    on_line(line.rstrip())
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass


def render_draft(job_dir: str, comp_name: str = "comp.html", out_name: str = "draft.mp4",
                 dur: float = 15.0, workers: int = 4, on_line=None,
                 sfx_name: str | None = None) -> str:
    """1080p30 草稿渲染（快门运动模糊）。→ mp4 绝对路径。

    sfx_name：job 目录内的音频文件名（audio.py 产出的 sfx.wav），传给
    render.py --sfx 混入成片；None 为无声版。
    注意：render.py 以 cwd 解析 --out，必须传相对文件名（cwd=job_dir）。"""

    ensure_environment()
    cmd = [
        sys.executable,
        os.path.join(SCRIPTS_DIR, "render.py"),
        comp_name,
        "--out",
        out_name,
        "--dur",
        str(dur),
        "--workers",
        str(max(1, min(8, int(workers)))),
    ]
    if sfx_name:
        cmd += ["--sfx", sfx_name]
    code, output = _run(cmd, cwd=job_dir, timeout=RENDER_TIMEOUT_S, on_line=on_line)
    out = os.path.join(job_dir, out_name)
    if code != 0 or not os.path.isfile(out):
        tail = "\n".join(output.splitlines()[-8:])
        raise RuntimeError("onetake 渲染失败：{}".format(tail or "exit {}".format(code)))
    return out


def extract_poster(job_dir: str, video: str, at: float = 12.9, out_name: str = "poster.png") -> str:
    """成片海报帧（默认取 end card wordmark 帧）。用绝对 exe 路径——Windows
    CreateProcess 按**父进程** PATH 解析可执行名，不认 Popen 注入的 env。"""

    ffmpeg, _ffprobe = _ff_binaries()
    if not ffmpeg:
        raise RenderEnvironmentError("未找到 ffmpeg/static-ffmpeg：`python -m pip install static-ffmpeg`")
    out = os.path.join(job_dir, out_name)
    cmd = [
        ffmpeg, "-v", "error", "-y",
        "-ss", "{:.2f}".format(at), "-i", video,
        "-frames:v", "1", out,
    ]
    code, _ = _run(cmd, cwd=job_dir, timeout=60.0)
    if code != 0 or not os.path.isfile(out):
        raise RuntimeError("海报帧提取失败")
    return out


def verify_film(job_dir: str, video_name: str = "draft.mp4", comp_name: str = "comp.html",
                shots: list[float] | None = None) -> tuple[bool, str]:
    """验收 oracle（rhythm/rest/burst/continuity/curves/framing）。→ (passed, report)。"""

    ensure_environment()
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "verify_promo.py"), video_name, "--comp", comp_name]
    if shots:
        cmd += ["--shots", ",".join("{:.2f}".format(t) for t in shots)]
    env = _env()
    env["PYTHONPATH"] = SCRIPTS_DIR + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(  # noqa: S603
        cmd, cwd=job_dir, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=VERIFY_TIMEOUT_S,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
