"""Runs every activity rule over each observation."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from mantau_core.contracts import EventKind, FallEvent
from mantau_core.contracts.detection import DetectionSettings, ZoneKind

from .geometry import zone_at
from .observations import FrameObservation
from .tracking import Step, TrackingConfig, TrackRegistry

log = logging.getLogger(__name__)

# Seconds of field coverage, by state. Drained by `drain_coverage`.
COVERAGE_STATES = ("no_person", "one_person", "multi_person", "low_confidence", "outage")


@runtime_checkable
class ActivityRule(Protocol):
    """One feature's state machine. `update` must be fast and never block:
    it runs on the detection path for every observation. It receives a
    tracking `Step` (stable local ids, confidence, and the seconds its timers
    may count -- 0 while paused), never raw detector output."""

    kind: EventKind

    def update(self, step: Step, settings: DetectionSettings) -> list[FallEvent]:
        """Events this step causes, usually none."""
        ...

    def reset(self) -> None:
        """Forget all state (settings changed or the camera reconnected)."""
        ...


class ActivityEngine:
    """Feeds observations to rules with the current settings.

    - Ignores people standing in EXCLUDED zones (TVs, mirrors, windows).
    - Skips rules whose feature is disabled in the settings.
    - A failing rule is logged and isolated; it never stops the others or
      the fall path.
    - Counts seconds of coverage per state (`COVERAGE_STATES`) for field
      trials; that bookkeeping never changes the events emitted.
    """

    def __init__(self, rules: Iterable[ActivityRule] = (),
                 settings: DetectionSettings | None = None,
                 tracking: TrackingConfig | None = None) -> None:
        self.rules = list(rules)
        self.settings = settings or DetectionSettings()
        self.failures: dict[str, int] = {}
        self.tracking = TrackRegistry(tracking or TrackingConfig())
        self._last_at: datetime | None = None
        self._lost_since_last = False
        self._coverage: dict[str, float] = dict.fromkeys(COVERAGE_STATES, 0.0)

    def camera_lost(self) -> None:
        """The camera stream dropped. Timers pause; nothing that changes
        across the outage counts as someone arriving or leaving."""
        self.tracking.camera_lost()
        self._lost_since_last = True

    def drain_coverage(self) -> dict[str, float]:
        """Seconds per coverage state since the last drain (zeros included),
        then reset them to zero."""
        totals = self._coverage
        self._coverage = dict.fromkeys(COVERAGE_STATES, 0.0)
        return totals

    def _count_coverage(self, at: datetime, step: Step) -> None:
        previous, self._last_at = self._last_at, at
        lost, self._lost_since_last = self._lost_since_last, False
        if previous is None:
            return
        elapsed = (at - previous).total_seconds()
        if elapsed <= 0:
            # Repeated or regressed clock: nothing counts, and `at` is the new base.
            return
        if lost or elapsed > self.tracking.config.max_frame_gap_s:
            self._coverage["outage"] += elapsed
        else:
            self._coverage[_coverage_state(step)] += elapsed

    def apply_settings(self, settings: DetectionSettings) -> None:
        if settings.version != self.settings.version or settings != self.settings:
            # Recording and stream-quality changes do not change what the rules
            # decide, so an episode in progress (someone on the floor) survives them.
            unrelated = {"version", "recordings", "stream"}
            delivery_only = (
                (settings.recordings != self.settings.recordings
                 or settings.stream != self.settings.stream)
                and settings.model_dump(exclude=unrelated)
                == self.settings.model_dump(exclude=unrelated)
            )
            self.settings = settings
            if not delivery_only:
                for rule in self.rules:
                    rule.reset()

    def update(self, observation: FrameObservation) -> list[FallEvent]:
        excluded = self.settings.zones_of(ZoneKind.EXCLUDED)
        if excluded:
            people = tuple(p for p in observation.people
                           if zone_at(*p.anchor, excluded) is None)
            if len(people) != len(observation.people):
                observation = FrameObservation(
                    camera_id=observation.camera_id, at=observation.at, people=people)
        step = self.tracking.step(observation)
        try:
            self._count_coverage(observation.at, step)
        except Exception as exc:  # noqa: BLE001 -- coverage must never reach the rules
            log.warning("coverage bookkeeping failed (%s)", type(exc).__name__)
        events: list[FallEvent] = []
        for rule in self.rules:
            if not self._enabled(rule.kind):
                continue
            try:
                events.extend(rule.update(step, self.settings))
            except Exception as exc:  # noqa: BLE001 -- isolate one bad rule
                name = type(rule).__name__
                self.failures[name] = self.failures.get(name, 0) + 1
                log.warning("activity rule %s failed (%s)", name, type(exc).__name__)
        return events

    def _enabled(self, kind: EventKind) -> bool:
        settings = self.settings
        return {
            EventKind.STILLNESS: settings.stillness.enabled,
            EventKind.NOCTURNAL_MOVEMENT: settings.nocturnal.enabled,
            EventKind.BATHROOM_DURATION: settings.bathroom.enabled,
            EventKind.FALL: settings.fall.enabled,
        }.get(kind, True)


def _coverage_state(step: Step) -> str:
    """Which coverage state a tracked step is in (after excluded zones are gone)."""
    people = step.people
    if not people:
        return "no_person"
    if len(people) >= 2:
        return "multi_person"
    return "one_person" if people[0].confident else "low_confidence"
