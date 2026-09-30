"""Tiny software rasterizer for smooth 2D artwork (pure stdlib).

The first-generation renderer was pixel art (32x32 grid, nearest upscale).
This module is the opposite: a resolution-independent, anti-aliased polygon
rasterizer with source-over alpha compositing, used to draw soft cartoon
characters from ellipse / capsule / polygon primitives.

* analytic per-scanline span filling (no per-pixel inside tests),
* vertical + horizontal coverage anti-aliasing (sub-scanlines),
* uniform polygon outset for cartoon outlines,
* no third-party dependencies.
"""

import math
from collections import defaultdict


class Surface:
    """RGBA byte buffer with source-over compositing."""

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.buf = bytearray(width * height * 4)

    def blend(self, x, y, r, g, b, a):
        if a <= 0 or x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        i = (y * self.w + x) * 4
        buf = self.buf
        da = buf[i + 3]
        if da == 0 or a >= 255:
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = a if da == 0 else 255
            return
        sa = a / 255.0
        dca = da / 255.0
        outa = sa + dca * (1.0 - sa)
        inv = dca * (1.0 - sa)
        buf[i] = int((r * sa + buf[i] * inv) / outa + 0.5)
        buf[i + 1] = int((g * sa + buf[i + 1] * inv) / outa + 0.5)
        buf[i + 2] = int((b * sa + buf[i + 2] * inv) / outa + 0.5)
        buf[i + 3] = int(outa * 255.0 + 0.5)

    def to_rgba(self):
        return bytes(self.buf)


def _span(cov, width, xa, xb, weight):
    if xb <= xa:
        return
    if xa < 0:
        xa = 0
    if xb > width:
        xb = width
    if xb <= xa:
        return
    i0 = int(xa)
    i1 = int(xb)
    if i0 == i1:
        cov[i0] += (xb - xa) * weight
        return
    cov[i0] += (i0 + 1 - xa) * weight
    for i in range(i0 + 1, i1):
        cov[i] += weight
    if i1 < width:
        cov[i1] += (xb - i1) * weight


def fill_polygon(surface, points, color, alpha=255, ss=4):
    """Fill a (possibly concave) polygon with anti-aliasing."""
    n = len(points)
    if n < 3 or alpha <= 0:
        return
    r, g, b = color
    width, height = surface.w, surface.h
    ys = [p[1] for p in points]
    py0 = max(0, int(math.floor(min(ys))))
    py1 = min(height - 1, int(math.ceil(max(ys))))
    if py1 < py0:
        return

    edges = []
    for k in range(n):
        x0, y0 = points[k]
        x1, y1 = points[(k + 1) % n]
        if y0 == y1:
            continue
        if y0 < y1:
            ey0, ey1, ex0, slope = y0, y1, x0, (x1 - x0) / (y1 - y0)
        else:
            ey0, ey1, ex0, slope = y1, y0, x1, (x1 - x0) / (y1 - y0)
        edges.append((ey0, ey1, ex0, slope))

    buckets = defaultdict(list)
    for edge in edges:
        buckets[max(0, int(math.floor(edge[0])))].append(edge)

    active = []
    weight = 1.0 / ss
    for py in range(py0, py1 + 1):
        if buckets.get(py):
            active.extend(buckets[py])
        if active:
            active = [e for e in active if e[1] > py]
        if not active:
            continue
        cov = [0.0] * width
        for s in range(ss):
            yy = py + (s + 0.5) / ss
            xs = [ex0 + (yy - ey0) * slope for (ey0, ey1, ex0, slope) in active if ey0 <= yy < ey1]
            if len(xs) < 2:
                continue
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                _span(cov, width, xs[j], xs[j + 1], weight)
        for px in range(width):
            c = cov[px]
            if c <= 0.0:
                continue
            a = int(c * alpha + 0.5)
            if a <= 0:
                continue
            if a > 255:
                a = 255
            surface.blend(px, py, r, g, b, a)


# --------------------------------------------------------------------------
# primitive point generators (all in a shared coordinate space)
# --------------------------------------------------------------------------


def ellipse(cx, cy, rx, ry, n=64, rot=0.0):
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    points = []
    for i in range(n):
        a = 2.0 * math.pi * i / n
        x = math.cos(a) * rx
        y = math.sin(a) * ry
        if rot:
            x, y = x * cos_r - y * sin_r, x * sin_r + y * cos_r
        points.append((cx + x, cy + y))
    return points


def capsule(x0, y0, x1, y1, r, n=18):
    ang = math.atan2(y1 - y0, x1 - x0)
    points = []
    for i in range(n + 1):
        a = ang - math.pi / 2 + math.pi * i / n
        points.append((x1 + math.cos(a) * r, y1 + math.sin(a) * r))
    for i in range(n + 1):
        a = ang + math.pi / 2 + math.pi * i / n
        points.append((x0 + math.cos(a) * r, y0 + math.sin(a) * r))
    return points


def rounded_rect(x, y, w, h, r, n=8):
    r = min(r, w / 2, h / 2)
    points = []
    corners = (
        (x + w - r, y + r, -math.pi / 2, 0.0),
        (x + w - r, y + h - r, 0.0, math.pi / 2),
        (x + r, y + h - r, math.pi / 2, math.pi),
        (x + r, y + r, math.pi, 3 * math.pi / 2),
    )
    for cx, cy, a0, a1 in corners:
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            points.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return points


def polygon(points):
    return list(points)


def offset_polygon(points, d):
    """Uniform outward offset (for cartoon outlines) via averaged normals."""
    n = len(points)
    if n < 3 or d == 0:
        return list(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    out = []
    for i in range(n):
        px, py = points[i - 1]
        qx, qy = points[i]
        rx, ry = points[(i + 1) % n]

        e1x, e1y = qx - px, qy - py
        e2x, e2y = rx - qx, ry - qy
        l1 = math.hypot(e1x, e1y) or 1.0
        l2 = math.hypot(e2x, e2y) or 1.0
        nx = -e1y / l1 - e2y / l2
        ny = e1x / l1 + e2x / l2
        ln = math.hypot(nx, ny) or 1.0
        nx /= ln
        ny /= ln
        if (qx - cx) * nx + (qy - cy) * ny < 0:
            nx, ny = -nx, -ny
        out.append((qx + nx * d, qy + ny * d))
    return out
