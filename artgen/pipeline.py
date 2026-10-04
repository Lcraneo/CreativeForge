"""Animation pipeline: image -> style/character analysis -> style-consistent
frames -> consistency validation -> animated GIF + sprite sheet.

Ties together the deterministic renderer (``artgen.anim``), the style/feature
analyser (``artgen.style``) and the pure-stdlib media codec (``artgen.gif``).
"""

import io

from artgen.anim import ACTIONS, pack_sheet, render_action_frames
from artgen.character2d import asset_params, render_character_view
from artgen.gif import decode_image, decode_png, encode_gif
from artgen.png import encode_rgba
from artgen.style import analyze_rgba, extract_character, similarity_rgba


def _to_rgba(source):
    """PNG/JPEG/WebP bytes | (w,h,rgba) | None -> (w,h,rgba) | None."""
    if source is None:
        return None
    if isinstance(source, (tuple, list)) and len(source) == 3:
        return source
    if isinstance(source, (bytes, bytearray)):
        return decode_image(bytes(source))
    raise TypeError("reference must be image bytes, (w,h,rgba) or None")


def analyze_source(source):
    """Style + character profile of the input image."""
    reference = _to_rgba(source)
    if reference is None:
        return None
    width, height, rgba = reference
    profile = analyze_rgba(width, height, rgba)
    return {"style": profile, "character": extract_character(width, height, rgba)}


def compose_animation(
    frame_bytes=None,
    frames_rgba=None,
    fps=12,
    size=384,
    loop=True,
    consistency_floor=0.6,
    with_mp4=True,
    mp4_dst_fps=None,
):
    """Compose an animation from user-supplied sequence frames (the standard
    sprite workflow): each frame is decoded and contain-fitted onto a shared
    size×size canvas, then packed into GIF + sheet with a consistency check
    against the first frame.

    ``frame_bytes`` is a list of PNG/JPEG/WebP bytes; ``frames_rgba`` may be
    passed instead as ready (w,h,RGBA) tuples.
    """
    from PIL import Image

    from artgen.sourceanim import _fit

    fps = max(1, min(60, int(fps)))
    size = max(64, min(1024, int(size)))

    if frames_rgba is None:
        if not frame_bytes:
            raise ValueError("no frames supplied")
        frames_rgba = []
        for data in frame_bytes[:90]:
            frame = Image.open(io.BytesIO(data)).convert("RGBA")
            canvas = _fit(frame, size)
            frames_rgba.append((size, size, bytearray(canvas.tobytes())))
    if len(frames_rgba) < 2:
        raise ValueError("a sequence needs at least 2 frames")

    frames_rgba = [(w, h, bytearray(rgba)) for w, h, rgba in frames_rgba]
    reference_rgba = tuple(frames_rgba[0])

    style = analyze_rgba(*reference_rgba)
    character = extract_character(*reference_rgba)

    step = max(1, len(frames_rgba) // 6)
    sampled = frames_rgba[::step]
    per_frame = [similarity_rgba(reference_rgba, frame) for frame in sampled]
    aggregate = {
        key: round(sum(item[key] for item in per_frame) / len(per_frame), 4)
        for key in ("palette", "color", "line", "hash", "overall")
    }
    aggregate["passed"] = aggregate["overall"] >= consistency_floor
    aggregate["floor"] = consistency_floor
    aggregate["frames_checked"] = len(per_frame)

    gif = encode_gif(
        [rgba for _, _, rgba in frames_rgba], size, size, fps=fps, loop=0 if loop else 1
    )
    sheet_w, sheet_h, sheet_rgba = pack_sheet(frames_rgba)
    sheet = encode_rgba(sheet_w, sheet_h, sheet_rgba)

    # mp4 出口（V3 后期链）：与 GIF 同帧交付 CRF16 H.264，可选运动补偿
    # 补帧到 dst_fps。无 ffmpeg 时为 None，GIF 兜底不受影响。
    mp4 = None
    mp4_fps = fps
    if with_mp4:
        from artgen.postfx import finalize_mp4

        mp4, mp4_fps = finalize_mp4(frames_rgba, size, size, fps, dst_fps=mp4_dst_fps)

    return {
        "action": "sequence",
        "fps": fps,
        "duration": round(len(frames_rgba) / fps, 3),
        "frame_count": len(frames_rgba),
        "size": size,
        "loop": loop,
        "style": style,
        "character": character,
        "consistency": aggregate,
        "per_frame": per_frame,
        "gif": gif,
        "sheet": sheet,
        "sheet_size": [sheet_w, sheet_h],
        "frames": [encode_rgba(size, size, rgba) for _, _, rgba in frames_rgba],
        "mp4": mp4,
        "mp4_fps": mp4_fps,
    }


def create_animation(
    params=None,
    asset=None,
    action="walk",
    fps=12,
    duration=1.0,
    size=512,
    frames=None,
    reference=None,
    source_bytes=None,
    loop=True,
    consistency_floor=0.6,
    view="front",
    pose_config=None,
    segment_mask=None,
    rigged=False,
    overlays=None,
):
    """Build a style-consistent animation.

    ``params``/``asset`` select the vector character; ``source_bytes`` is the
    real source image (PNG/JPEG bytes) — when present the animation is driven
    from that exact artwork (source-driven), keeping content/style/composition.
    ``reference`` is a style anchor for the vector path when no source is given.
    ``view="side"`` switches walk/run to the dedicated side-view gait system
    (2D 平台游戏式横版行走); ``pose_config`` carries the custom-action sliders.
    ``segment_mask`` is an optional external subject mask for the source-driven
    path (see artgen.sourceanim.animate_source).
    """
    action = action if action in ACTIONS else "walk"
    render_params = params or (asset_params(asset) if asset is not None else None)
    if render_params is None:
        render_params = {"seed": f"{action}-{fps}", "palette": None}

    fps = max(1, min(60, int(fps)))
    duration = max(0.1, min(10.0, float(duration)))
    # 上限 90：放行 24fps×~3.5s 的整循环（旧 48 封顶把 24fps 循环挡在门外）。
    # 内存口径：90 帧×384² RGBA ≈ 53MB 原始 + PIL 编码峰值，抽帧链本就流式，
    # 显式请求大帧数才触达。
    frame_count = int(frames) if frames else max(2, min(90, round(fps * duration)))
    frame_count = max(2, min(90, frame_count))
    size = max(64, min(1024, int(size)))

    # 1) frames: rig-driven (character-bound) > source-driven > side gait > vector
    source_reference = None
    rig = None
    falign = None
    if rigged and source_bytes:
        from artgen.riganim import animate_rigged

        frames_rgba, source_reference, rig, falign = animate_rigged(
            source_bytes,
            action,
            frame_count,
            size,
            config=pose_config,
            segment_mask=segment_mask,
            overlays=overlays,
        )
    elif source_bytes:
        from artgen.sourceanim import animate_source

        frames_rgba, source_reference = animate_source(
            source_bytes, action, frame_count, size, segment_mask=segment_mask
        )
    elif view == "side" and action in ("walk", "run"):
        from artgen.sidewalk import render_side_frames

        frames_rgba = render_side_frames(render_params, action, frame_count, size, pose_config)
    else:
        frames_rgba = render_action_frames(render_params, action, frame_count, size, pose_config)

    # 2) reference for style matching
    reference_rgba = source_reference or _to_rgba(reference)
    if reference_rgba is None:
        # fall back to the asset's still image as the style anchor
        anchor_view = "side" if (view == "side" and action in ("walk", "run")) else "front"
        still = render_character_view(render_params, anchor_view, size)
        reference_rgba = decode_png(still)

    style = analyze_rgba(*reference_rgba)
    character = extract_character(*reference_rgba)

    # 3) per-frame consistency + aggregate
    step = max(1, frame_count // 6)
    sampled = frames_rgba[::step]
    per_frame = [similarity_rgba(reference_rgba, frame) for frame in sampled]
    aggregate = {
        key: round(sum(item[key] for item in per_frame) / len(per_frame), 4)
        for key in ("palette", "color", "line", "hash", "overall")
    }
    aggregate["passed"] = aggregate["overall"] >= consistency_floor
    aggregate["floor"] = consistency_floor
    aggregate["frames_checked"] = len(per_frame)

    # 4) encode animated GIF + sprite sheet
    gif = encode_gif(
        [rgba for _, _, rgba in frames_rgba], size, size, fps=fps, loop=0 if loop else 1
    )
    sheet_w, sheet_h, sheet_rgba = pack_sheet(frames_rgba)
    sheet = encode_rgba(sheet_w, sheet_h, sheet_rgba)

    # mp4 出口（V3 后期链）：同 compose_animation
    mp4 = None
    mp4_fps = fps
    from artgen.postfx import finalize_mp4

    mp4, mp4_fps = finalize_mp4(frames_rgba, size, size, fps)

    return {
        "action": action,
        "fps": fps,
        "duration": round(frame_count / fps, 3),
        "frame_count": frame_count,
        "size": size,
        "loop": loop,
        "style": style,
        "character": character,
        "consistency": aggregate,
        "per_frame": per_frame,
        "rig": rig,
        "falign": falign,
        "gif": gif,
        "sheet": sheet,
        "sheet_size": [sheet_w, sheet_h],
        "frames": [encode_rgba(size, size, rgba) for _, _, rgba in frames_rgba],
        "mp4": mp4,
        "mp4_fps": mp4_fps,
    }
