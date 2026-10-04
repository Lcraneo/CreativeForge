"""后期处理链（V3）：程序化动画的 mp4 交付出口与运动补偿补帧。

V1 给 i2v 链做了 mp4 直通交付；本模块把同等的交付规格带给程序化链
（骨骼/源图/序列帧）——它们此前唯一的动态产物是 384~512px 的 GIF：

  encode_mp4        RGBA 帧序列 -> H.264 CRF16 high profile +faststart
                    （与 onetake 渲染规范一致；透明帧合成到指定底色，
                    yuv420p 要求偶数尺寸，奇数自动补 1px）
  interpolate_mci   低帧率 mp4 -> 24fps 运动补偿补帧（ffmpeg minterpolate
                    MCI/AOBMC，CPU 本地零额度；RIFE ncnn 是后续可选升级位，
                    接口保持 mp4 bytes in/out 以便替换）

无 ffmpeg 环境（imageio-ffmpeg 缺失）时全部返回 None，调用方回退 GIF，
绝不阻塞生成。
"""

import os

# mp4 无透明通道，透明帧需合成底色。默认用前端暖纸视觉的 #f1efe9（与
# 动画工作台预览面板同色），成片在 UI 里无缝融入面板而非一块白斑。
WARM_PAPER_BG = (241, 239, 233)


def _composite_rgb(frames, width, height, bg):
    """(w,h,RGBA bytearray) 列表 -> RGB PIL 图列表（缩放到统一画布 +
    底色合成）。"""
    from PIL import Image

    images = []
    for w, h, rgba in frames:
        img = Image.frombytes("RGBA", (w, h), bytes(rgba))
        if (w, h) != (width, height):
            img = img.resize((width, height), Image.LANCZOS)
        base = Image.new("RGBA", (width, height), bg + (255,))
        base.alpha_composite(img)
        images.append(base.convert("RGB"))
    return images


def _pad_even(value):
    return int(value) + 1 if int(value) % 2 else int(value)


def encode_mp4(frames, width, height, fps=12, bg=WARM_PAPER_BG, crf=16):
    """RGBA 帧序列 -> mp4 bytes（libx264 CRF16 high profile +faststart）。

    imageio 的 ffmpeg 插件不支持 BytesIO 写入，走临时文件中转。返回 None
    的情形：帧数 <2 或无 ffmpeg 环境——调用方按"无 mp4"降级，GIF 产物
    不受影响。"""
    import os
    import tempfile

    try:
        import numpy as np

        import imageio.v2 as imageio
    except ImportError:
        return None
    frames = list(frames)
    if len(frames) < 2:
        return None
    width, height = _pad_even(width), _pad_even(height)
    images = _composite_rgb(frames, width, height, bg)
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        writer = imageio.get_writer(
            tmp_path,
            format="ffmpeg",
            fps=max(1, int(fps)),
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=1,  # 尺寸已自行补偶，禁用 16px 自动缩放
            ffmpeg_params=[
                "-profile:v", "high",
                "-crf", str(int(crf)),
                "-movflags", "+faststart",
                "-an",
            ],
        )
        try:
            for img in images:
                writer.append_data(np.asarray(img))
        finally:
            writer.close()
        with open(tmp_path, "rb") as handle:
            data = handle.read()
    except Exception:  # noqa: BLE001 - 编码失败降级为无 mp4
        return None
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return data if len(data) > 256 else None


def interpolate_mci(mp4_bytes, dst_fps=24, src_fps=None, crf=16):
    """低帧率 mp4 -> 运动补偿补帧到 dst_fps（ffmpeg minterpolate）。

    MCI+AOBMC+双向估计对角色循环动作的中间帧重建质量明显优于 blend
    （blend 会产生双影）。任何失败返回 None，调用方沿用原 mp4。"""
    if not mp4_bytes or len(mp4_bytes) < 1024:
        return None
    import subprocess
    import tempfile

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
    src_fd, src_path = tempfile.mkstemp(suffix=".mp4")
    out_fd, out_path = tempfile.mkstemp(suffix=".mp4")
    import os

    os.close(src_fd)
    os.close(out_fd)
    try:
        with open(src_path, "wb") as handle:
            handle.write(mp4_bytes)
        command = [
            ffmpeg, "-v", "error", "-y",
            "-i", src_path,
            "-vf",
            "minterpolate=fps={}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1".format(
                int(dst_fps)
            ),
            "-c:v", "libx264",
            "-crf", str(int(crf)),
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-movflags", "+faststart",
            "-an",
            out_path,
        ]
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        )
        proc = subprocess.run(
            command,
            timeout=300,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
        )
        if proc.returncode != 0 or os.path.getsize(out_path) < 256:
            return None
        with open(out_path, "rb") as handle:
            return handle.read()
    except Exception:  # noqa: BLE001 - 补帧失败沿用原片
        return None
    finally:
        for path in (src_path, out_path):
            try:
                os.remove(path)
            except OSError:
                pass


def finalize_mp4(frames, width, height, fps, dst_fps=None, bg=WARM_PAPER_BG):
    """一键出口：编码 + 可选补帧到 dst_fps。返回 (mp4_bytes, out_fps)，
    无 ffmpeg 时返回 (None, fps)。"""
    mp4 = encode_mp4(frames, width, height, fps=fps, bg=bg)
    if mp4 is None:
        return None, fps
    if dst_fps and dst_fps > fps:
        interpolated = interpolate_mci(mp4, dst_fps=dst_fps)
        if interpolated is not None:
            return interpolated, dst_fps
    return mp4, fps
