"""Deterministic seeding helpers for the PReCon pixel engine.

All four PReCon submodules (``contour`` / ``grid`` / ``palette`` / ``quality``)
derive their prompt-specific variation from a single seed so that the benchmark
stays reproducible. When no seed is available (the frozen benchmark baseline)
every helper degrades to ``None`` so callers keep their seedless behaviour.
"""

import colorsys
import random as _random


def seed_of(image):
    """Return a stable integer seed for ``image`` or ``None`` for the
    seedless benchmark path.

    ``image`` is the asset/character dict; a seed may arrive under the
    ``seed`` key (int or numeric string).
    """

    if not isinstance(image, dict):
        return None
    seed = image.get("seed")
    if seed is None:
        return None
    try:
        return int(seed)
    except (TypeError, ValueError):
        return None


def rng(seed, salt=0):
    """Return a 0..1 float generator deterministic for ``(seed, salt)``."""

    base = int(seed) if isinstance(seed, (int, float)) else 0
    state = (base ^ (salt * 0x9E3779B1)) & 0xFFFFFFFF
    gen = _random.Random(state)
    return gen.random


def clamp(value, lo=0.0, hi=1.0):
    """Clamp ``value`` into ``[lo, hi]`` (defaults to the unit interval)."""

    try:
        value = float(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, value))


def _hex_to_rgb(hex_color):
    text = str(hex_color).lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(
        "{:02x}".format(max(0, min(255, int(round(c)))) ) for c in rgb
    )


def shade(hex_color, amount):
    """Lighten (``amount`` > 0) or darken (``amount`` < 0) a hex colour.

    ``amount`` is a fraction in roughly (-1, 1): ``0.18`` nudges toward white,
    ``-0.45`` toward black.
    """

    rgb = _hex_to_rgb(hex_color)
    if amount >= 0:
        return _rgb_to_hex([c + (255 - c) * amount for c in rgb])
    factor = 1.0 + amount
    return _rgb_to_hex([c * factor for c in rgb])


def hue_palette(seed):
    """Deterministic 16-colour hue ramp derived from ``seed``."""

    base = int(seed) if isinstance(seed, (int, float)) else 0
    gen = _random.Random((base ^ 0x5BD1E995) & 0xFFFFFFFF)
    colors = []
    for index in range(16):
        hue = (index / 16.0 + gen.uniform(-0.02, 0.02)) % 1.0
        saturation = 0.45 + 0.35 * gen.random()
        value = 0.45 + 0.45 * gen.random()
        red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
        colors.append(_rgb_to_hex([red * 255, green * 255, blue * 255]))
    return colors
