"""What a perception model reports about one frame. Coordinates are
normalized (0..1, origin top-left), matching `DetectionSettings` zones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from mantau_core.contracts import FallEvent


class Posture(str, Enum):
    STANDING = "standing"
    SITTING = "sitting"
    LYING = "lying"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PersonObservation:
    track_id: int
    # Normalized bounding box: left, top, width, height.
    bbox: tuple[float, float, float, float]
    posture: Posture = Posture.UNKNOWN
    # Movement since the previous observation of this track, as a fraction
    # of the frame diagonal. 0 = perfectly still.
    motion: float = 0.0
    confidence: float = 1.0

    @property
    def anchor(self) -> tuple[float, float]:
        """Where the person is on the floor plane: bottom-center of the box."""
        left, top, width, height = self.bbox
        return left + width / 2, top + height


@dataclass(frozen=True)
class FrameObservation:
    camera_id: str
    # Wall-clock, timezone-aware. Night windows are evaluated in the
    # household timezone from this.
    at: datetime
    people: tuple[PersonObservation, ...] = ()


@dataclass(frozen=True)
class Perception:
    """One frame's output from a perceiving detector: falls it confirmed plus
    the observation the activity rules consume."""

    events: list[FallEvent] = field(default_factory=list)
    observation: FrameObservation | None = None
