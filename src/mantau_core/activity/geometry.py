"""Zone lookup in normalized image coordinates."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from mantau_core.contracts.detection import Point, Zone, ZoneKind


def point_in_polygon(x: float, y: float, polygon: Sequence[Point]) -> bool:
    """Even-odd ray casting. Points exactly on an edge may fall either way,
    which is irrelevant at camera resolution."""
    inside = False
    count = len(polygon)
    for i in range(count):
        a, b = polygon[i], polygon[(i + 1) % count]
        if (a.y > y) != (b.y > y):
            crossing = a.x + (y - a.y) * (b.x - a.x) / (b.y - a.y)
            if x < crossing:
                inside = not inside
    return inside


def zone_at(x: float, y: float, zones: Iterable[Zone],
            kinds: Iterable[ZoneKind] | None = None) -> Zone | None:
    """First zone containing the point, optionally only of `kinds`."""
    wanted = set(kinds) if kinds is not None else None
    for zone in zones:
        if wanted is not None and zone.kind not in wanted:
            continue
        if point_in_polygon(x, y, zone.polygon):
            return zone
    return None
