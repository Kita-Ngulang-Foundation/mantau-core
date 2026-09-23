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


class Zone(_Model):
    zone_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    kind: ZoneKind
    name: str = Field(default="", max_length=40)
    polygon: list[Point] = Field(min_length=3, max_length=32)


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
