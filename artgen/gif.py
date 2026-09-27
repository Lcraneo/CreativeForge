"""Pure-stdlib animated GIF encoder + PNG decoder.

No Pillow required: CreativeForge ships a hand-rolled GIF89a writer (median-cut
palette + LZW) and an 8-bit PNG reader (all five filter types, RGB/RGBA/gray).
This keeps animation output dependency-free and deterministic.
"""

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
        raise ValueError(
            "unsupported image format — install Pillow for JPEG/WebP/GIF"
        ) from error
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
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
            if interlace:
                raise ValueError("interlaced PNG not supported")
        elif tag == b"PLTE":
            palette = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk), 3)]
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
        line = bytearray(raw[offset:offset + stride])
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
            out[row:row + width * 4] = line
        elif color_type == 2:
            for x in range(width):
                r, g, b = line[x * 3:x * 3 + 3]
                out[row + x * 4:row + x * 4 + 4] = bytes((r, g, b, 255))
        elif color_type == 0:
            for x in range(width):
                v = line[x]
                out[row + x * 4:row + x * 4 + 4] = bytes((v, v, v, 255))
        elif color_type == 4:
            for x in range(width):
                v, a = line[x * 2:x * 2 + 2]
                out[row + x * 4:row + x * 4 + 4] = bytes((v, v, v, a))
        elif color_type == 3:
            for x in range(width):
                idx = line[x]
                r, g, b = palette[idx]
                a = trns[idx] if trns and idx < len(trns) else 255
                out[row + x * 4:row + x * 4 + 4] = bytes((r, g, b, a))
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
    return tuple(
        max(p[i] for p in box) - min(p[i] for p in box) for i in range(3)
    )


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


def encode_gif(frames, width, height, fps=12, loop=0, max_colors=255):
    """frames: list of RGBA bytearrays/bytes. Returns animated GIF bytes."""
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
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01" + struct.pack("<H", loop) + b"\x00"

    delay = max(2, round(100.0 / max(1, fps)))
    min_code_size = 8
    for indexed in indexed_frames:
        out += b"\x21\xF9\x04\x01" + struct.pack("<H", delay) + b"\x00\x00"  # GCE
        out += b"\x2C" + struct.pack("<HHHH", 0, 0, width, height) + b"\x00"
        out += bytes((min_code_size,)) + _lzw_encode(indexed, min_code_size)
    out += b"\x3B"
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
        dictionary[combined] = next_code
        next_code += 1
        if next_code == (1 << code_size):
            if code_size < 12:
                code_size += 1
            else:
                emit(clear)
                dictionary = {bytes((i,)): i for i in range(clear)}
                next_code = end + 1
                code_size = min_code_size + 1
        prefix = current
    if prefix:
        emit(dictionary[prefix])
    emit(end)
    if bit_count > 0:
        out.append(bit_buffer & 0xFF)
    blocks = bytearray()
    for i in range(0, len(out), 255):
        chunk = out[i:i + 255]
        blocks.append(len(chunk))
        blocks += chunk
    blocks.append(0)
    return bytes(blocks)
