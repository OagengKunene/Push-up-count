"""Small, dependency-free geometry helpers, operating in pixel coordinates."""

import math
from collections.abc import Sequence

Point = Sequence[float]


def angle(a: Point, b: Point, c: Point) -> float | None:
    """Interior angle ABC, or None for coincident/non-finite points."""
    values = [float(v) for point in (a, b, c) for v in point[:2]]
    if not all(math.isfinite(v) for v in values):
        return None
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    denominator = math.hypot(*u) * math.hypot(*v)
    if denominator <= 1e-9:
        return None
    cosine = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / denominator))
    return math.degrees(math.acos(cosine))


def horizontal_tilt(a: Point, b: Point) -> float:
    """Undirected tilt relative to horizontal in degrees, from 0 to 90."""
    return math.degrees(math.atan2(abs(b[1] - a[1]), abs(b[0] - a[0])))
