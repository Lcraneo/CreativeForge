"""Animation pipeline: image -> style/character analysis -> style-consistent
frames -> consistency validation -> animated GIF + sprite sheet.

Ties together the deterministic renderer (``artgen.anim``), the style/feature
analyser (``artgen.style``) and the pure-stdlib media codec (``artgen.gif``).
"""

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
):
    """Build a style-consistent animation.

    ``params``/``asset`` select the vector character; ``source_bytes`` is the
    real source image (PNG/JPEG bytes) — when present the animation is driven
    from that exact artwork (source-driven), keeping content/style/composition.
    ``reference`` is a style anchor for the vector path when no source is given.
    """
    action = action if action in ACTIONS else "walk"
    render_params = params or (asset_params(asset) if asset is not None else None)
    if render_params is None:
        render_params = {"seed": f"{action}-{fps}", "palette": None}

    fps = max(1, min(60, int(fps)))
    duration = max(0.1, min(10.0, float(duration)))
    frame_count = int(frames) if frames else max(2, min(48, round(fps * duration)))
    frame_count = max(2, min(48, frame_count))
    size = max(64, min(1024, int(size)))

    # 1) frames: source-driven (animate the actual artwork) or vector pose
    source_reference = None
    if source_bytes:
        from artgen.sourceanim import animate_source

        frames_rgba, source_reference = animate_source(source_bytes, action, frame_count, size)
    else:
        frames_rgba = render_action_frames(render_params, action, frame_count, size)

    # 2) reference for style matching
    reference_rgba = source_reference or _to_rgba(reference)
    if reference_rgba is None:
        # fall back to the asset's still image as the style anchor
        still = render_character_view(render_params, "front", size)
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
        "gif": gif,
        "sheet": sheet,
        "sheet_size": [sheet_w, sheet_h],
        "frames": [encode_rgba(size, size, rgba) for _, _, rgba in frames_rgba],
    }
