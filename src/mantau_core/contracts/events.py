"""Event shapes — what a detector produces and what travels over the wire.

These are pydantic models (not the plain dataclasses mantau-ai uses internally)
because they cross a process boundary at least once in every deployment: agent
-> server over HTTP, backend -> app as a JSON API response, backend -> FCM as
a push payload. `model_dump(mode="json")` / `model_validate_json()` is the
one (de)serialization path everyone should use.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class EventKind(str, Enum):
    """What kind of detection this is.

    The brief's roadmap includes more than falls (prolonged stillness,
    nocturnal movement, bathroom duration) — this enum exists so adding one
    later is a new member, not a new contract that every consumer has to
    learn about again.
    """

    FALL = "fall"
    STILLNESS = "stillness"
    NOCTURNAL_MOVEMENT = "nocturnal_movement"
    BATHROOM_DURATION = "bathroom_duration"


class Severity(str, Enum):
    """Urgency, independent of *what* was detected.

    A fall is CRITICAL by default. Anomaly kinds (once built) will mostly be
    WARNING/INFO — this is what the notify layer keys its channel choice and
    escalation policy off of, not `EventKind` directly.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


DEFAULT_SEVERITY: dict[EventKind, Severity] = {
    EventKind.FALL: Severity.CRITICAL,
    # Not moving for too long can be fainting or a stroke: as urgent as a fall.
    EventKind.STILLNESS: Severity.CRITICAL,
    EventKind.BATHROOM_DURATION: Severity.WARNING,
    EventKind.NOCTURNAL_MOVEMENT: Severity.WARNING,
}


def default_severity(kind: EventKind) -> Severity:
    """Starting urgency for a kind. Detectors may raise it (e.g. a bathroom
    visit that keeps growing becomes CRITICAL) but should not lower a fall."""
    return DEFAULT_SEVERITY.get(kind, Severity.WARNING)


class ClipRef(BaseModel):
    """A short annotated review clip around the event, generated best-effort.

    Mirrors mantau-ai's demo/backend clip attachment: clip generation can
    fail without failing the event itself, so `available` starts False and
    flips True once (if) the clip actually exists.
    """

    clip_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    url: str | None = None
    pre_s: float = 3.0
    post_s: float = 3.0
    available: bool = False


class FallEvent(BaseModel):
    """The event a Detector emits and that ends up in a push notification.

    `signals` is a deliberately open bag (not fixed fields) for the
    rule-based explainability data mantau-ai already computes — velocity,
    aspect_ratio, torso_angle_deg, etc. New signals from that repo never
    require a contract change here.
    """

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    camera_id: str
    kind: EventKind = EventKind.FALL
    severity: Severity = Severity.CRITICAL
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    track_id: int | None = None
    signals: dict[str, float] = Field(default_factory=dict)
    clip: ClipRef | None = None
    # Which of the household's zones an activity event happened in (its
    # user-chosen id, never coordinates). None for falls and unzoned events.
    zone_id: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")

    def with_clip(self, clip: ClipRef) -> "FallEvent":
        """Return a copy with the clip attached (events are immutable once emitted)."""
        return self.model_copy(update={"clip": clip})


class Heartbeat(BaseModel):
    """Liveness ping — from an RTSP worker (Scenario 1) or an agent (Scenario 2).

    `queue_depth` surfaces the buffer/spool backlog so a dashboard can show
    "camera is up but events are piling up" before an alert is ever late.
    """

    agent_id: str
    camera_id: str | None = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    camera_reachable: bool
    detector_alive: bool
    queue_depth: int = 0
