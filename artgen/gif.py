"""Pure-stdlib animated GIF encoder + PNG decoder.

Pillow is used for GIF writing when available (spec-perfect LZW); without it a
conservative hand-rolled GIF89a writer (median-cut palette + fixed-width LZW)
and an 8-bit PNG reader (all five filter types, RGB/RGBA/gray) keep animation
output dependency-free and deterministic.
"""

import io
import struct
import zlib

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def decode_image(data):
    """Decode PNG natively; fall back to Pillow for JPEG/WebP/GIF/BMP.

    -> (width, height, RGBA bytearray). Raises ValueError on failure.
    """
    if data[:8] == PNG_MAGIC:
        return decode_png(data)
    try:
        from PIL import Image  # optional dependency
    except ImportError as error:  # pragma: no cover
        raise ValueError("unsupported image format — install Pillow for JPEG/WebP/GIF") from error
    import io

    try:
        with Image.open(io.BytesIO(data)) as handle:
            rgba = handle.convert("RGBA")
            return rgba.width, rgba.height, bytearray(rgba.tobytes())
    except Exception as error:  # noqa: BLE001
        raise ValueError(f"cannot decode image: {error}") from error


# --------------------------------------------------------------------------
# PNG decode
# --------------------------------------------------------------------------


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data: bytes):
    """-> (width, height, bytearray RGBA). Raises ValueError on unsupported."""
    if data[:8] != PNG_MAGIC:
        raise ValueError("not a PNG")
    pos = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    palette = None
    trns = None
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            if interlace:
                raise ValueError("interlaced PNG not supported")
        elif tag == b"PLTE":
            palette = [tuple(chunk[i : i + 3]) for i in range(0, len(chunk), 3)]
        elif tag == b"tRNS":
            trns = chunk
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break

    if bit_depth != 8:
        raise ValueError(f"unsupported bit depth {bit_depth}")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"unsupported color type {color_type}")

    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    prev = bytearray(stride)
    out = bytearray(width * height * 4)
    offset = 0
    for y in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset : offset + stride])
        offset += stride
        if filter_type == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                up_left = prev[i - channels] if i >= channels else 0
                line[i] = (line[i] + _paeth(left, prev[i], up_left)) & 0xFF
        elif filter_type != 0:
            raise ValueError(f"unknown filter {filter_type}")
        row = y * width * 4
        if color_type == 6:
            out[row : row + width * 4] = line
        elif color_type == 2:
            for x in range(width):
                r, g, b = line[x * 3 : x * 3 + 3]
                out[row + x * 4 : row + x * 4 + 4] = bytes((r, g, b, 255))
        elif color_type == 0:
            for x in range(width):
                v = line[x]
                out[row + x * 4 : row + x * 4 + 4] = bytes((v, v, v, 255))
        elif color_type == 4:
            for x in range(width):
                v, a = line[x * 2 : x * 2 + 2]
                out[row + x * 4 : row + x * 4 + 4] = bytes((v, v, v, a))
        elif color_type == 3:
            for x in range(width):
                idx = line[x]
                r, g, b = palette[idx]
                a = trns[idx] if trns and idx < len(trns) else 255
                out[row + x * 4 : row + x * 4 + 4] = bytes((r, g, b, a))
        prev = line
    return width, height, out


# --------------------------------------------------------------------------
# GIF encode
# --------------------------------------------------------------------------


def _median_cut(pixels, max_colors):
    boxes = [pixels]
    while len(boxes) < max_colors:
        boxes.sort(key=lambda box: max(_spread(box)[i] for i in range(3)), reverse=True)
        box = boxes.pop(0)
        channel = max(range(3), key=lambda i: _spread(box)[i])
        box.sort(key=lambda p: p[channel])
        mid = len(box) // 2
        if mid == 0:
            boxes.append(box)
            break
        boxes.append(box[:mid])
        boxes.append(box[mid:])
    return [_average(box) for box in boxes[:max_colors]]


def _spread(box):
    if not box:
        return (0, 0, 0)
    return tuple(max(p[i] for p in box) - min(p[i] for p in box) for i in range(3))


def _average(box):
    n = max(1, len(box))
    return tuple(sum(p[i] for p in box) // n for i in range(3))


def _nearest(palette, color):
    best, best_d = 0, 1 << 30
    for index, entry in enumerate(palette):
        d = (entry[0] - color[0]) ** 2 + (entry[1] - color[1]) ** 2 + (entry[2] - color[2]) ** 2
        if d < best_d:
            best, best_d = index, d
    return best


def encode_gif(frames, width, height, fps=12, loop=0, max_colors=255, dither=None):
    """frames: list of RGBA bytearrays/bytes. Returns animated GIF bytes.

    Prefers Pillow's encoder (spec-perfect LZW + per-frame disposal); the
    hand-rolled LZW historically produced streams that strict decoders
    truncate mid-frame, which rendered as flickering previews. Without
    Pillow, a conservative stdlib encoder is used that clears the table
    before any code-width change could ever be needed.

    Palette strategy: ONE global palette is built from all frames (see
    _build_global_palette) and applied to every frame — per-frame palettes
    made identical colors drift between frames. ``dither`` (Image.Dither
    int) defaults to NONE — A/B verified 2026-10-04 (gradient-ball fixture,
    adjacent-frame correlation): NONE 0.87393 vs FLOYDSTEINBERG 0.87375
    mean with ~zero flicker variance for both, while dither costs +7% bytes;
    the global palette already removes inter-frame color drift, so dither
    only re-rolls per-frame noise. Keep NONE unless a real clip proves
    otherwise.
    """
    try:
        from PIL import Image
    except ImportError:
        return _encode_gif_stdlib(frames, width, height, fps, loop, max_colors)

    duration_ms = max(20, round(1000.0 / max(1, fps)))
    images = [Image.frombytes("RGBA", (width, height), bytes(frame)) for frame in frames]
    reserve_transparent = any(
        im.getchannel("A").getextrema()[0] < 128 for im in images
    )
    palette_img = _build_global_palette(images, max_colors, reserve_transparent)
    dither_mode = Image.Dither.NONE if dither is None else Image.Dither(dither)
    quantized = [
        _quantize_frame_global(im, palette_img, dither_mode, reserve_transparent)
        for im in images
    ]

    buf = io.BytesIO()
    kwargs = {
        "save_all": True,
        "append_images": quantized[1:],
        "duration": duration_ms,
        # `loop` is the raw NETSCAPE loop count: 0 = loop forever. Never map
        # it through a truthiness check — 0 is the *wanted* value and would
        # invert to "play once then freeze on the last frame".
        "loop": max(0, min(65535, int(loop))),
        "disposal": 2,  # restore-to-background: no ghosting between frames
        "optimize": False,
    }
    if reserve_transparent:
        kwargs["transparency"] = 0
    quantized[0].save(buf, "GIF", **kwargs)
    return buf.getvalue()


def _build_global_palette(images, max_colors, reserve_transparent):
    """Cross-frame global palette: nearest-downsample every frame (NEAREST
    keeps source colors, averaging would invent new ones), pool the samples
    and median-cut once. Per-frame palettes quantize each frame against a
    different color set, so identical source colors drift between frames —
    visible as inter-frame color shimmer on flat regions."""
    from PIL import Image

    side = max(16, min(128, int((8192 / max(1, len(images))) ** 0.5)))
    samples = []
    for im in images:
        samples.extend(im.convert("RGB").resize((side, side), Image.NEAREST).getdata())
    if not samples:
        samples = [(0, 0, 0)]
    colors = max(2, min(256, max_colors)) - (1 if reserve_transparent else 0)
    strip = Image.new("RGB", (len(samples), 1))
    strip.putdata(samples)
    return strip.quantize(colors=colors, method=Image.MEDIANCUT)


def _quantize_frame_global(im, palette_img, dither, reserve_transparent):
    """Map one RGBA frame onto the shared palette. When the sequence has any
    transparency, palette index 0 is reserved for it (declared via
    info["transparency"]); opaque colors therefore live at index >= 1."""
    from PIL import Image

    p = im.convert("RGB").quantize(palette=palette_img, dither=dither)
    if not reserve_transparent:
        return p
    shifted = p.point(lambda i: min(255, i + 1))
    alpha = im.getchannel("A")
    opaque = alpha.point(lambda a: 0 if a < 128 else 255)
    out = Image.composite(shifted, Image.new("P", im.size, 0), opaque)
    palette = (palette_img.getpalette() or [])[: 255 * 3]
    out.putpalette([0, 0, 0] + palette + [0] * (768 - 3 - len(palette)))
    out.info["transparency"] = 0
    return out


def _encode_gif_stdlib(frames, width, height, fps=12, loop=0, max_colors=255):
    """Pillow-free animated GIF writer (conservative LZW, fixed code width)."""
    # sample palette from all opaque pixels
    sample = []
    step = max(1, (width * height) // 4000)
    for frame in frames:
        for i in range(0, width * height, step):
            o = i * 4
            if frame[o + 3] >= 128:
                sample.append((frame[o], frame[o + 1], frame[o + 2]))
    if not sample:
        sample = [(0, 0, 0)]
    # index 0 reserved for transparency
    palette = [(0, 0, 0)] + _median_cut(sample, max(1, max_colors))
    while len(palette) < 2:
        palette.append((0, 0, 0))

    indexed_frames = []
    cache = {}
    for frame in frames:
        indexed = bytearray(width * height)
        for i in range(width * height):
            o = i * 4
            if frame[o + 3] < 128:
                indexed[i] = 0
                continue
            color = (frame[o], frame[o + 1], frame[o + 2])
            idx = cache.get(color)
            if idx is None:
                idx = _nearest(palette[1:], color) + 1
                cache[color] = idx
            indexed[i] = idx
        indexed_frames.append(indexed)

    out = bytearray(b"GIF89a")
    out += struct.pack("<HH", width, height)
    out += bytes((0xF7, 0, 0))  # global table, 256 entries
    for r, g, b in palette[:256]:
        out += bytes((r, g, b))
    for _ in range(256 - len(palette[:256])):
        out += b"\x00\x00\x00"

    # netscape loop extension
    out += b"\x21\xff\x0bNETSCAPE2.0\x03\x01" + struct.pack("<H", loop) + b"\x00"

    delay = max(2, round(100.0 / max(1, fps)))
    min_code_size = 8
    for indexed in indexed_frames:
        # GCE flags 0x05 = disposal method 2 (restore to background) + has
        # transparency index; with plain 0x01 browsers keep showing the
        # previous frame through transparent pixels, so moving subjects ghost
        # and the loop appears to flicker
        out += b"\x21\xf9\x04\x05" + struct.pack("<H", delay) + b"\x00\x00"  # GCE
        out += b"\x2c" + struct.pack("<HHHH", 0, 0, width, height) + b"\x00"
        out += bytes((min_code_size,)) + _lzw_encode(indexed, min_code_size)
    out += b"\x3b"
    return bytes(out)


def _lzw_encode(indexed, min_code_size):
    clear = 1 << min_code_size
    end = clear + 1
    code_size = min_code_size + 1
    dictionary = {bytes((i,)): i for i in range(clear)}
    next_code = end + 1

    out = bytearray()
    bit_buffer = 0
    bit_count = 0

    def emit(code):
        nonlocal bit_buffer, bit_count
        bit_buffer |= code << bit_count
        bit_count += code_size
        while bit_count >= 8:
            out.append(bit_buffer & 0xFF)
            bit_buffer >>= 8
            bit_count -= 8

    emit(clear)
    prefix = b""
    for value in indexed:
        current = bytes((value,))
        combined = prefix + current
        if combined in dictionary:
            prefix = combined
            continue
        emit(dictionary[prefix] if prefix else value)
        if next_code >= (1 << code_size) - 1:
            # table nearly full: clear before any code-width change could be
            # required. Widening the code size mid-stream is where decoder
            # conventions disagree ("early change"), so this fixed-width
            # scheme decodes identically everywhere.
            emit(clear)
            dictionary = {bytes((i,)): i for i in range(clear)}
            next_code = end + 1
        else:
            dictionary[combined] = next_code
            next_code += 1
        prefix = current
    if prefix:
        emit(dictionary[prefix])
    emit(end)
    if bit_count > 0:
        out.append(bit_buffer & 0xFF)
    blocks = bytearray()
    for i in range(0, len(out), 255):
        chunk = out[i : i + 255]
        blocks.append(len(chunk))
        blocks += chunk
    blocks.append(0)
    return bytes(blocks)
