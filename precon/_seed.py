"""Deterministic helpers shared by the PReCon stages.

A generation request carries a ``seed`` (derived from the user prompt) plus a
semantic palette; both let every stage produce prompt-specific yet fully
reproducible results. When no seed is present the stages fall back to the
frozen baseline values used by the benchmark.
"""

import hashlib


def to_seed(value):
    """Normalizes a seed (int or string) to a 32-bit int, or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value & 0xFFFFFFFF
    text = str(value).encode("utf-8")
    return int(hashlib.sha1(text).hexdigest()[:8], 16)


def seed_of(image):
    if not isinstance(image, dict):
        return None
    return to_seed(image.get("seed"))


def rng(seed, salt=0):
    """Tiny LCG -> deterministic float stream in [0, 1)."""
    value = (int(seed) ^ (0x9E3779B9 * (salt + 1))) & 0xFFFFFFFF

    def next_float():
        nonlocal value
        value = (value * 1664525 + 1013904223) & 0xFFFFFFFF
        return value / 0xFFFFFFFF

    return next_float


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))


def _channel(value):
    return max(0, min(255, int(round(value))))


def hex_to_rgb(color):
    text = str(color).lstrip("#")
    if len(text) == 3:
        text = "".join(char * 2 for char in text)
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(_channel(value) for value in rgb))


def shade(color, amount):
    """Lightens (amount > 0) or darkens (amount < 0) a hex colour."""
    red, green, blue = hex_to_rgb(color)
    if amount >= 0:
        factor = amount
        red, green, blue = (
            red + (255 - red) * factor,
            green + (255 - green) * factor,
            blue + (255 - blue) * factor,
        )
    else:
        factor = 1.0 + amount
        red, green, blue = red * factor, green * factor, blue * factor
    return rgb_to_hex((red, green, blue))


def hue_palette(seed, count=16):
    """Builds a deterministic 16-colour ramp from a seed (hue rotation)."""
    import colorsys

    hue = (int(seed) % 360) / 360.0
    ramps = [
        (0.16, 0.10), (0.16, 0.20), (0.16, 0.32), (0.30, 0.48),
        (0.42, 0.62), (0.52, 0.72), (0.60, 0.82), (0.22, 0.42),
    ]
    colors = []
    for index in range(count):
        saturation, lightness = ramps[index % len(ramps)]
        hue_shift = (hue + index * 0.013) % 1.0
        red, green, blue = colorsys.hls_to_rgb(hue_shift, lightness, saturation)
        colors.append(rgb_to_hex((red * 255, green * 255, blue * 255)))
    return colors
