"""Runs every activity rule over each observation."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from mantau_core.contracts import EventKind, FallEvent
from mantau_core.contracts.detection import DetectionSettings, ZoneKind

from .geometry import zone_at
from .observations import FrameObservation
from .tracking import Step, TrackingConfig, TrackRegistry

log = logging.getLogger(__name__)


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
    """

    def __init__(self, rules: Iterable[ActivityRule] = (),
                 settings: DetectionSettings | None = None,
                 tracking: TrackingConfig | None = None) -> None:
        self.rules = list(rules)
        self.settings = settings or DetectionSettings()
        self.failures: dict[str, int] = {}
        self.tracking = TrackRegistry(tracking or TrackingConfig())

    def camera_lost(self) -> None:
        """The camera stream dropped. Timers pause; nothing that changes
        across the outage counts as someone arriving or leaving."""
        self.tracking.camera_lost()

    def apply_settings(self, settings: DetectionSettings) -> None:
        if settings.version != self.settings.version or settings != self.settings:
            self.settings = settings
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
