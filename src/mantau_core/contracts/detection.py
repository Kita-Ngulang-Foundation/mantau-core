"""Per-camera detection settings -- what each Mantau feature needs to know
about a room, set by the family in the app and applied on the agent.

Stored by the server per camera, delivered to the agent with the
`apply_detection_settings` control command, and read by the activity rules
(`mantau_core.activity`). Coordinates are normalized to the camera frame
(0..1, origin top-left) so a zone survives a resolution or substream change.
"""

from __future__ import annotations

from datetime import time
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ZoneKind(str, Enum):
    """What a region of the image means to the rules."""

    BED = "bed"                        # nocturnal: leaving/returning to bed
    BATHROOM_DOOR = "bathroom_door"    # bathroom duration: entering/leaving
    FLOOR = "floor"                    # stillness: lying here is urgent
    SEATING = "seating"                # stillness: resting here is normal longer
    EXCLUDED = "excluded"              # ignored everywhere (TV, window, mirror)


class Point(_Model):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


MIN_ZONE_AREA = 0.0005  # 0.05% of the frame: smaller is a mis-tap, not a zone


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)


def _on_segment(p: Point, a: Point, b: Point) -> bool:
    return (min(a.x, b.x) <= p.x <= max(a.x, b.x)
            and min(a.y, b.y) <= p.y <= max(a.y, b.y))


def _segments_touch(a: Point, b: Point, c: Point, d: Point) -> bool:
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True
    return ((d1 == 0 and _on_segment(a, c, d)) or (d2 == 0 and _on_segment(b, c, d))
            or (d3 == 0 and _on_segment(c, a, b)) or (d4 == 0 and _on_segment(d, a, b)))


def polygon_problem(polygon: list[Point]) -> str | None:
    """Why a zone outline cannot be used, or None. Degenerate outlines
    (repeated corners, no area) and self-intersecting ones (a bow tie has no
    well-defined inside) are rejected."""
    count = len(polygon)
    if len({(p.x, p.y) for p in polygon}) != count:
        return "polygon repeats a corner"
    area = abs(sum(polygon[i].x * polygon[(i + 1) % count].y
                   - polygon[(i + 1) % count].x * polygon[i].y for i in range(count))) / 2
    for i in range(count):
        a, b = polygon[i], polygon[(i + 1) % count]
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue  # neighbours share a corner
            if _segments_touch(a, b, polygon[j], polygon[(j + 1) % count]):
                return "polygon edges cross"
    if area < MIN_ZONE_AREA:
        return "polygon has no usable area"
    return None


class Zone(_Model):
    zone_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    kind: ZoneKind
    name: str = Field(default="", max_length=40)
    polygon: list[Point] = Field(min_length=3, max_length=32)

    @model_validator(mode="after")
    def usable_polygon(self) -> "Zone":
        problem = polygon_problem(self.polygon)
        if problem is not None:
            raise ValueError(problem)
        return self


class FallSettings(_Model):
    enabled: bool = True
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class StillnessSettings(_Model):
    enabled: bool = True
    # Lying still on the floor is urgent; sitting still on a sofa is normal
    # for much longer.
    floor_minutes: float = Field(default=2.0, ge=0.5, le=60.0)
    other_minutes: float = Field(default=45.0, ge=5.0, le=240.0)


class NocturnalSettings(_Model):
    enabled: bool = True
    start: time = time(22, 0)
    end: time = time(5, 0)
    out_of_bed_minutes: float = Field(default=20.0, ge=1.0, le=180.0)
    max_bed_exits: int = Field(default=3, ge=1, le=20)


class BathroomSettings(_Model):
    enabled: bool = True
    warning_minutes: float = Field(default=20.0, ge=1.0, le=180.0)
    # A visit still going at this point escalates to CRITICAL.
    critical_minutes: float = Field(default=40.0, ge=1.0, le=240.0)

    @model_validator(mode="after")
    def critical_after_warning(self) -> "BathroomSettings":
        if self.critical_minutes < self.warning_minutes:
            raise ValueError("critical_minutes must not be before warning_minutes")
        return self


class DetectionSettings(_Model):
    """The whole per-camera configuration. `version` increases with every
    change so the agent can report which one it is running."""

    schema_version: int = 1
    version: int = Field(default=1, ge=1)
    timezone: str = "Asia/Jakarta"
    fall: FallSettings = Field(default_factory=FallSettings)
    stillness: StillnessSettings = Field(default_factory=StillnessSettings)
    nocturnal: NocturnalSettings = Field(default_factory=NocturnalSettings)
    bathroom: BathroomSettings = Field(default_factory=BathroomSettings)
    zones: list[Zone] = Field(default_factory=list, max_length=16)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown timezone") from exc
        return value

    @model_validator(mode="after")
    def unique_zone_ids(self) -> "DetectionSettings":
        ids = [zone.zone_id for zone in self.zones]
        if len(ids) != len(set(ids)):
            raise ValueError("zone ids must be unique")
        return self

    def zones_of(self, kind: ZoneKind) -> list[Zone]:
        return [zone for zone in self.zones if zone.kind is kind]
