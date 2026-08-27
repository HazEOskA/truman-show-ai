"""Planar geometry for the projection engine.

Pure functions over ``(x, y)`` tuples in metres. No dependency on the kernel, on domain
state or on numpy: the projection has to reproduce byte-for-byte on any machine that runs
the simulation, so it uses the same stdlib-only arithmetic as the rest of Hydra.

Winding is counter-clockwise and areas are signed accordingly. Every routine here assumes
simple (non self-intersecting) polygons; the pipeline only ever produces those.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Vec2 = tuple[float, float]
Polygon = list[Vec2]

EPS = 1e-9


# -- vectors ----------------------------------------------------------------------


def add(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] - b[0], a[1] - b[1])


def scale(a: Vec2, k: float) -> Vec2:
    return (a[0] * k, a[1] * k)


def dot(a: Vec2, b: Vec2) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Vec2, b: Vec2) -> float:
    return a[0] * b[1] - a[1] * b[0]


def length(a: Vec2) -> float:
    return math.hypot(a[0], a[1])


def distance(a: Vec2, b: Vec2) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalise(a: Vec2) -> Vec2:
    n = length(a)
    if n < EPS:
        return (0.0, 0.0)
    return (a[0] / n, a[1] / n)


def perpendicular(a: Vec2) -> Vec2:
    """Left normal."""

    return (-a[1], a[0])


def lerp(a: Vec2, b: Vec2, t: float) -> Vec2:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def rotate(a: Vec2, angle: float) -> Vec2:
    c, s = math.cos(angle), math.sin(angle)
    return (a[0] * c - a[1] * s, a[0] * s + a[1] * c)


# -- polygons ---------------------------------------------------------------------


def signed_area(poly: Sequence[Vec2]) -> float:
    total = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total * 0.5


def area(poly: Sequence[Vec2]) -> float:
    return abs(signed_area(poly))


def centroid(poly: Sequence[Vec2]) -> Vec2:
    a = signed_area(poly)
    if abs(a) < EPS:
        if not poly:
            return (0.0, 0.0)
        return (
            sum(p[0] for p in poly) / len(poly),
            sum(p[1] for p in poly) / len(poly),
        )
    cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    k = 1.0 / (6.0 * a)
    return (cx * k, cy * k)


def ensure_ccw(poly: Sequence[Vec2]) -> Polygon:
    return list(poly) if signed_area(poly) >= 0 else list(reversed(poly))


def bbox(points: Iterable[Vec2]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for x, y in points:
        xs.append(x)
        ys.append(y)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def contains(poly: Sequence[Vec2], point: Vec2) -> bool:
    """Ray casting. Points exactly on an edge may fall either way; callers use margins."""

    x, y = point
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            t = (y - y1) / (y2 - y1)
            if x < x1 + t * (x2 - x1):
                inside = not inside
    return inside


def clip_halfplane(poly: Sequence[Vec2], normal: Vec2, offset: float) -> Polygon:
    """Sutherland-Hodgman clip to ``dot(normal, p) <= offset``."""

    if not poly:
        return []
    out: Polygon = []
    n = len(poly)
    for i in range(n):
        cur = poly[i]
        nxt = poly[(i + 1) % n]
        d_cur = dot(normal, cur) - offset
        d_nxt = dot(normal, nxt) - offset
        if d_cur <= 0.0:
            out.append(cur)
        if (d_cur > 0.0) != (d_nxt > 0.0):
            denom = d_cur - d_nxt
            if abs(denom) > EPS:
                out.append(lerp(cur, nxt, d_cur / denom))
    return out


def clip_convex(poly: Sequence[Vec2], clipper: Sequence[Vec2]) -> Polygon:
    """Clip ``poly`` against a convex CCW ``clipper``."""

    result = list(poly)
    n = len(clipper)
    for i in range(n):
        a = clipper[i]
        b = clipper[(i + 1) % n]
        edge = sub(b, a)
        normal = (edge[1], -edge[0])          # outward for CCW clipper
        result = clip_halfplane(result, normal, dot(normal, a))
        if not result:
            return []
    return result


def offset_inward(poly: Sequence[Vec2], amount: float) -> Polygon:
    """Shrink a convex-ish polygon by clipping each edge inward.

    Used for setbacks. On strongly concave polygons this over-cuts; parcels are convex by
    construction, so that never happens in the pipeline.
    """

    if amount <= 0.0:
        return list(poly)
    result = list(poly)
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        edge = sub(b, a)
        normal = (edge[1], -edge[0])
        norm = length(normal)
        if norm < EPS:
            continue
        unit = (normal[0] / norm, normal[1] / norm)
        result = clip_halfplane(result, unit, dot(unit, a) - amount)
        if len(result) < 3:
            return []
    return result


def resample(poly: Sequence[Vec2], count: int) -> Polygon:
    """Even-arclength resample of a closed polygon. Keeps vertex budgets predictable."""

    if len(poly) < 3 or count < 3:
        return list(poly)
    lengths = []
    total = 0.0
    n = len(poly)
    for i in range(n):
        d = distance(poly[i], poly[(i + 1) % n])
        lengths.append(d)
        total += d
    if total < EPS:
        return list(poly)
    step = total / count
    out: Polygon = []
    seg = 0
    walked = 0.0
    for i in range(count):
        target = i * step
        while seg < n - 1 and walked + lengths[seg] < target:
            walked += lengths[seg]
            seg += 1
        remain = target - walked
        d = lengths[seg]
        t = 0.0 if d < EPS else remain / d
        out.append(lerp(poly[seg], poly[(seg + 1) % n], min(1.0, max(0.0, t))))
    return out


def simplify(poly: Sequence[Vec2], tolerance: float) -> Polygon:
    """Douglas-Peucker on a closed ring, anchored at the two most distant vertices."""

    pts = list(poly)
    if len(pts) < 4 or tolerance <= 0.0:
        return pts
    anchor = 0
    far = max(range(len(pts)), key=lambda i: distance(pts[anchor], pts[i]))
    first = pts[anchor : far + 1]
    second = pts[far:] + [pts[anchor]]
    kept = _dp(first, tolerance)[:-1] + _dp(second, tolerance)[:-1]
    return kept if len(kept) >= 3 else pts


def _dp(pts: Sequence[Vec2], tolerance: float) -> Polygon:
    if len(pts) < 3:
        return list(pts)
    start, end = pts[0], pts[-1]
    worst = 0.0
    index = 0
    for i in range(1, len(pts) - 1):
        d = point_segment_distance(pts[i], start, end)
        if d > worst:
            worst = d
            index = i
    if worst <= tolerance:
        return [start, end]
    left = _dp(pts[: index + 1], tolerance)
    right = _dp(pts[index:], tolerance)
    return left[:-1] + right


def point_segment_distance(p: Vec2, a: Vec2, b: Vec2) -> float:
    ab = sub(b, a)
    denom = dot(ab, ab)
    if denom < EPS:
        return distance(p, a)
    t = max(0.0, min(1.0, dot(sub(p, a), ab) / denom))
    return distance(p, add(a, scale(ab, t)))


def polyline_length(points: Sequence[Vec2]) -> float:
    return sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))


def rectangle(centre: Vec2, width: float, depth: float, angle: float) -> Polygon:
    """CCW rectangle, ``width`` along the rotated x axis."""

    hw, hd = width * 0.5, depth * 0.5
    corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    return [add(centre, rotate(c, angle)) for c in corners]


def oriented_extent(poly: Sequence[Vec2], angle: float) -> tuple[float, float]:
    """Width and depth of ``poly`` measured in a frame rotated by ``angle``."""

    if not poly:
        return (0.0, 0.0)
    c, s = math.cos(-angle), math.sin(-angle)
    xs = [p[0] * c - p[1] * s for p in poly]
    ys = [p[0] * s + p[1] * c for p in poly]
    return (max(xs) - min(xs), max(ys) - min(ys))


def round_point(p: Vec2, places: int = 2) -> Vec2:
    """Quantise to centimetres so the projection hash is stable across platforms."""

    return (round(p[0], places) + 0.0, round(p[1], places) + 0.0)
