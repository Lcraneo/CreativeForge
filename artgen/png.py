"""Minimal pure-stdlib RGBA PNG encoder.

No Pillow / numpy dependency: the CreativeForge pipeline is deterministic and
ships only the standard library, so we emit valid 8-bit non-interlaced RGBA
PNG files by hand (IHDR + IDAT + IEND, zlib deflate).
"""

import struct
import zlib

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_rgba(width: int, height: int, pixels: bytes) -> bytes:
    """Encode a raw RGBA buffer (len == width*height*4) into PNG bytes."""
    if len(pixels) != width * height * 4:
        raise ValueError("pixel buffer length %d != %d" % (len(pixels), width * height * 4))

    # filter byte (0 = None) per scanline
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += pixels[y * stride : (y + 1) * stride]

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        PNG_MAGIC
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )
