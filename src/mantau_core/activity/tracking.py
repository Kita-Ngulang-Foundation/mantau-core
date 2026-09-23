"""Tracking hygiene: turn raw per-frame observations into steps the activity
rules can time safely.

- Stable local ids: a person keeps one local id for as long as the detector
  keeps its track, and also across a short loss (occlusion, a missed frame)
  when a new detector track appears close to where the lost one was. Only
  position and time are used: no appearance, face or other biometric.
- Confidence: a person whose landmark visibility is below `min_confidence` is
  still tracked, but marked not confident so timers do not count them.
- Pausing: timers only ever add `Step.dt`. It is 0 for the first frame, after
  a camera outage (`camera_lost`), after a gap longer than `max_frame_gap_s`,
  and when time does not move forward (a regressed or repeated timestamp).
  So a disconnect or a clock jump pauses every timer rather than counting the
  missing time.

Rules are deterministic functions of steps; time comes only from the
observations (`FrameObservation.at`), never from the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import hypot

from .observations import FrameObservation, PersonObservation


@dataclass(frozen=True)
class TrackingConfig:
    min_confidence: float = 0.5
    # A track lost for at most this long and re-found within `reacquire_distance`
    # (normalized frame units, floor anchor) keeps its local id.
    reacquire_s: float = 30.0
    reacquire_distance: float = 0.15
    # Frames further apart than this are treated as an outage.
    max_frame_gap_s: float = 5.0


@dataclass(frozen=True)
class TrackedPerson:
    local_id: int
    observation: PersonObservation
    confident: bool

    @property
    def anchor(self) -> tuple[float, float]:
        return self.observation.anchor


@dataclass(frozen=True)
class LostTrack:
    """A person who was visible on the previous step and is not now."""

    local_id: int
    last: PersonObservation
    confident: bool

    @property
    def anchor(self) -> tuple[float, float]:
        return self.last.anchor


@dataclass(frozen=True)
class Step:
    camera_id: str
    at: datetime
    # Seconds timers may count for this step; 0 means paused.
    dt: float
    people: tuple[TrackedPerson, ...] = ()
    # Local ids first seen on this step (not re-acquired from a lost track).
    appeared: tuple[int, ...] = ()
    # Local ids re-acquired from a recently lost track.
    reacquired: tuple[int, ...] = ()
    lost: tuple[LostTrack, ...] = ()
    # True on the first step after a camera outage: disappearances and
    # appearances across the outage are not evidence of anything.
    after_outage: bool = False

    @property
    def confident_people(self) -> tuple[TrackedPerson, ...]:
        return tuple(p for p in self.people if p.confident)


@dataclass
class _Lost:
    local_id: int
    last: PersonObservation
    lost_at: datetime


@dataclass
class TrackRegistry:
    config: TrackingConfig = field(default_factory=TrackingConfig)
    _last_at: datetime | None = None
    _outage: bool = True
    _next_id: int = 1
    _by_track: dict[int, int] = field(default_factory=dict)          # detector id -> local id
    _current: dict[int, PersonObservation] = field(default_factory=dict)  # local id -> last obs
    _current_confident: dict[int, bool] = field(default_factory=dict)
    _lost: list[_Lost] = field(default_factory=list)

    def camera_lost(self) -> None:
        """The camera stream dropped: the next step pauses timers and nothing
        that changes across the outage counts as an appearance or departure."""
        self._outage = True

    def step(self, observation: FrameObservation) -> Step:
        at = observation.at
        if self._last_at is None or self._outage:
            dt = 0.0
        else:
            elapsed = (at - self._last_at).total_seconds()
            dt = elapsed if 0 < elapsed <= self.config.max_frame_gap_s else 0.0
        gap = self._last_at is not None and not self._outage and (
            (at - self._last_at).total_seconds() > self.config.max_frame_gap_s)
        after_outage = self._outage or gap
        self._outage = False
        # Always re-base on the newest observation: after a clock jump backwards
        # this step counts nothing and later steps count from the new time.
        self._last_at = at

        cfg = self.config
        self._lost = [lost for lost in self._lost
                      if 0 <= (at - lost.lost_at).total_seconds() <= cfg.reacquire_s]
        people, appeared, reacquired, seen = [], [], [], set()
        by_track: dict[int, int] = {}
        for obs in observation.people:
            local_id = self._by_track.get(obs.track_id)
            if local_id is None or local_id in seen:
                local_id = self._reacquire(obs, seen)
                if local_id is not None:
                    reacquired.append(local_id)
                else:
                    local_id = self._next_id
                    self._next_id += 1
                    appeared.append(local_id)
            seen.add(local_id)
            by_track[obs.track_id] = local_id
            people.append(TrackedPerson(local_id, obs, obs.confidence >= cfg.min_confidence))

        lost = tuple(LostTrack(local_id, obs, self._current_confident.get(local_id, False))
                     for local_id, obs in self._current.items() if local_id not in seen)
        for gone in lost:
            self._lost.append(_Lost(gone.local_id, gone.last, at))
        self._by_track = by_track
        self._current = {p.local_id: p.observation for p in people}
        self._current_confident = {p.local_id: p.confident for p in people}
        return Step(camera_id=observation.camera_id, at=at, dt=dt, people=tuple(people),
                    appeared=tuple(appeared), reacquired=tuple(reacquired), lost=lost,
                    after_outage=after_outage)

    def _reacquire(self, obs: PersonObservation, taken: set[int]) -> int | None:
        best, best_distance = None, self.config.reacquire_distance
        x, y = obs.anchor
        for lost in self._lost:
            if lost.local_id in taken:
                continue
            lx, ly = lost.last.anchor
            distance = hypot(x - lx, y - ly)
            if distance <= best_distance:
                best, best_distance = lost, distance
        if best is None:
            return None
        self._lost.remove(best)
        return best.local_id
