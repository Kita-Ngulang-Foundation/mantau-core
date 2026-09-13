"""One trace per fall event, stamped identically by both backends.

Stamps are wall-clock (epoch seconds), not `time.monotonic()`, because the
five stages happen on genuinely different machines — camera/agent, backend,
FCM, and the family's phone. That only gives an honest number if every
machine's clock is reasonably NTP-synced; good enough for a prototype, not a
substitute for real distributed tracing if this goes further.

DELIVERED is the pitch's actual promise ("family notifications in under 5
seconds") — ACKED is the fuller, better number (a human actually saw it) but
is not what "under 5 seconds" was ever claiming.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


class Stage(str, Enum):
    CAPTURED = "captured"      # camera frame timestamp
    DETECTED = "detected"      # Detector emitted the FallEvent
    QUEUED = "queued"          # entered the notify fanout
    SENT = "sent"              # handed to a push/telegram channel
    DELIVERED = "delivered"    # channel confirmed acceptance (the <5s promise)
    ACKED = "acked"            # a human opened the alert (bonus, not the promise)


STAGES: tuple[Stage, ...] = (
    Stage.CAPTURED, Stage.DETECTED, Stage.QUEUED, Stage.SENT, Stage.DELIVERED, Stage.ACKED,
)


@dataclass
class LatencyTrace:
    event_id: str
    clock: Callable[[], float] = field(default=time.time, repr=False, compare=False)
    _stamps: dict[Stage, float] = field(default_factory=dict)
    _acks: list[float] = field(default_factory=list)

    def stamp(self, stage: Stage, *, at: float | None = None) -> None:
        ts = at if at is not None else self.clock()
        if stage is Stage.ACKED:
            # Several devices may ack the same event; the headline number is
            # the FIRST person to see it, so keep every ack but latch the min.
            self._acks.append(ts)
            if Stage.ACKED not in self._stamps or ts < self._stamps[Stage.ACKED]:
                self._stamps[Stage.ACKED] = ts
        else:
            self._stamps[stage] = ts

    def has(self, stage: Stage) -> bool:
        return stage in self._stamps

    def elapsed(self, *, start: Stage = Stage.CAPTURED, end: Stage = Stage.DELIVERED) -> float | None:
        """Seconds from `start` to `end`, or None if either hasn't happened yet."""
        if start not in self._stamps or end not in self._stamps:
            return None
        return self._stamps[end] - self._stamps[start]

    def within_budget(self, seconds: float = 5.0, *, end: Stage = Stage.DELIVERED) -> bool | None:
        """True/False once measurable, None while still in flight."""
        e = self.elapsed(end=end)
        return None if e is None else e <= seconds

    def ack_count(self) -> int:
        return len(self._acks)

    def to_summary(self) -> dict[str, float | None]:
        """Per-stage seconds-since-CAPTURED, for a report table or an API response."""
        base = self._stamps.get(Stage.CAPTURED)
        if base is None:
            return {stage.value: None for stage in STAGES}
        return {
            stage.value: (self._stamps[stage] - base) if stage in self._stamps else None
            for stage in STAGES
        }
