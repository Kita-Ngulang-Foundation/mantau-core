"""The activity rules: prolonged position, nocturnal movement, bathroom duration.

Each rule is a deterministic state machine over tracking `Step`s (see
`tracking.py`) and the household's `DetectionSettings`. Time comes only from
the steps; a paused step (`dt == 0`) never advances a timer. Events carry
only what the family needs to act -- durations, counts, a movement score, a
confidence and the user-chosen zone id -- never coordinates, images or
anything that identifies a person.

Event ids are derived from the camera, rule, episode start and severity, so
the same episode always produces the same ids: a re-delivered event is a
duplicate the server can drop, never a second alert. The Android agent's
Kotlin port is held to these rules by the shared fixtures in
`fixtures/activity_sequences`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import hypot
from zoneinfo import ZoneInfo

from mantau_core.contracts import EventKind, FallEvent, Severity
from mantau_core.contracts.detection import DetectionSettings, Zone, ZoneKind

from .clock import in_window
from .geometry import zone_at
from .observations import Posture
from .tracking import Step, TrackedPerson

# A warning at the configured minutes; critical once twice as long has passed.
CRITICAL_FACTOR = 2.0
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def epoch_ms(at: datetime) -> int:
    return (at - _EPOCH) // timedelta(milliseconds=1)


def event_id(camera_id: str, kind: EventKind, key: str, severity: Severity) -> str:
    raw = f"{camera_id}|{kind.value}|{key}|{severity.value}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def make_event(step: Step, kind: EventKind, severity: Severity, key: str, *,
               signals: dict[str, float], confidence: float = 1.0,
               track_id: int | None = None, zone_id: str | None = None) -> FallEvent:
    return FallEvent(
        event_id=event_id(step.camera_id, kind, key, severity), camera_id=step.camera_id,
        kind=kind, severity=severity, occurred_at=step.at,
        confidence=min(max(confidence, 0.0), 1.0), track_id=track_id, signals=signals,
        zone_id=zone_id,
    )


def placed_zone(person_anchor: tuple[float, float], settings: DetectionSettings) -> Zone | None:
    """The first non-excluded zone containing the anchor (settings order)."""
    zones = [z for z in settings.zones if z.kind is not ZoneKind.EXCLUDED]
    return zone_at(*person_anchor, zones)


def _levels(elapsed_s: float, warning_s: float, fired: set[str]) -> list[Severity]:
    out = []
    if elapsed_s >= warning_s and "warning" not in fired:
        fired.add("warning")
        out.append(Severity.WARNING)
    if elapsed_s >= warning_s * CRITICAL_FACTOR and "critical" not in fired:
        fired.add("critical")
        out.append(Severity.CRITICAL)
    return out


# -- prolonged position ----------------------------------------------------------

MOVE_RADIUS = 0.05      # floor-anchor drift (normalized) that ends an immobility episode
STAND_UP_S = 3.0        # upright this long ends a lying-on-the-floor episode
FORGET_S = 600.0        # per-person state kept this long after they were last seen


@dataclass
class _Position:
    last_seen: datetime
    floor_start: datetime | None = None
    floor_s: float = 0.0
    floor_moved: float = 0.0
    floor_zone: str | None = None
    floor_fired: set[str] = field(default_factory=set)
    upright_s: float = 0.0
    still_start: datetime | None = None
    still_ref: tuple[float, float] | None = None
    still_s: float = 0.0
    still_moved: float = 0.0
    still_zone: str | None = None
    still_fired: set[str] = field(default_factory=set)


class ProlongedPositionRule:
    """A confident, continuously visible person lying on the floor past
    `floor_minutes`, or not moving elsewhere past `other_minutes`.

    Bed and seating zones are normal rest, and so is the night window for the
    "not moving" case (lying on the floor is still reported at night). Where
    the household drew no floor zone, lying anywhere outside bed and seating
    counts as the floor. Warning at the threshold, critical at twice it, each
    once per episode."""

    kind = EventKind.STILLNESS

    def __init__(self) -> None:
        self._people: dict[int, _Position] = {}

    def reset(self) -> None:
        self._people.clear()

    def update(self, step: Step, settings: DetectionSettings) -> list[FallEvent]:
        events: list[FallEvent] = []
        cfg = settings.stillness
        night = in_window(step.at, settings.nocturnal.start, settings.nocturnal.end,
                          settings.timezone)
        has_floor_zones = any(z.kind is ZoneKind.FLOOR for z in settings.zones)
        for person in step.people:
            state = self._people.setdefault(person.local_id, _Position(last_seen=step.at))
            state.last_seen = step.at
            if not person.confident:
                continue  # seen but not trusted: every timer pauses
            events += self._person(step, person, state, cfg.floor_minutes * 60,
                                   cfg.other_minutes * 60, night, has_floor_zones, settings)
        for local_id in [i for i, s in self._people.items()
                         if (step.at - s.last_seen).total_seconds() > FORGET_S]:
            del self._people[local_id]
        return events

    def _person(self, step: Step, person: TrackedPerson, state: _Position, floor_s: float,
                other_s: float, night: bool, has_floor_zones: bool,
                settings: DetectionSettings) -> list[FallEvent]:
        obs = person.observation
        zone = placed_zone(person.anchor, settings)
        kind = zone.kind if zone is not None else None
        resting = kind in (ZoneKind.BED, ZoneKind.SEATING)
        on_floor = (obs.posture is Posture.LYING and not resting
                    and (kind is ZoneKind.FLOOR or (kind is None and not has_floor_zones)))
        events = []

        if on_floor:
            if state.floor_start is None:
                state.floor_start, state.floor_s, state.floor_moved = step.at, 0.0, 0.0
                state.floor_zone = zone.zone_id if zone is not None else None
                state.floor_fired = set()
            state.floor_s += step.dt
            state.floor_moved += obs.motion
            state.upright_s = 0.0
            for severity in _levels(state.floor_s, floor_s, state.floor_fired):
                events.append(self._event(step, person, severity, "floor", state.floor_start,
                                          state.floor_s, state.floor_moved, state.floor_zone))
        elif state.floor_start is not None:
            if resting:
                state.floor_start = None
            elif obs.posture in (Posture.STANDING, Posture.SITTING):
                state.upright_s += step.dt
                if state.upright_s >= STAND_UP_S:
                    state.floor_start = None

        if resting or on_floor:
            state.still_start = state.still_ref = None
            return events
        if night:
            return events  # normal rest at night: the immobility timer pauses
        if state.still_ref is None or hypot(person.anchor[0] - state.still_ref[0],
                                            person.anchor[1] - state.still_ref[1]) > MOVE_RADIUS:
            state.still_start, state.still_ref = step.at, person.anchor
            state.still_s, state.still_moved = 0.0, 0.0
            state.still_zone = zone.zone_id if zone is not None else None
            state.still_fired = set()
            return events
        state.still_s += step.dt
        state.still_moved += obs.motion
        for severity in _levels(state.still_s, other_s, state.still_fired):
            events.append(self._event(step, person, severity, "still", state.still_start,
                                      state.still_s, state.still_moved, state.still_zone))
        return events

    def _event(self, step: Step, person: TrackedPerson, severity: Severity, branch: str,
               started: datetime, duration_s: float, moved: float,
               zone_id: str | None) -> FallEvent:
        return make_event(
            step, self.kind, severity, f"{branch}:{person.local_id}@{epoch_ms(started)}",
            signals={"duration_s": round(duration_s, 1), "movement": round(moved, 4),
                     "confidence": round(person.observation.confidence, 3)},
            confidence=person.observation.confidence, track_id=person.local_id, zone_id=zone_id)


# -- nocturnal movement ------------------------------------------------------------

BED_SETTLE_S = 60.0       # in bed at least this long before leaving counts as a bed exit
EXIT_CONFIRM_S = 10.0     # out of bed this long confirms an exit
RETURN_CONFIRM_S = 10.0   # back in bed this long ends the out-of-bed episode
ZONE_SETTLE_S = 3.0       # a zone change counts once it has lasted this long
WANDER_TRANSITIONS = 8    # zone changes in one out-of-bed night that count as wandering


@dataclass
class _Night:
    key: str
    exits: int = 0
    fired: set[str] = field(default_factory=set)
    in_bed_s: float = 0.0
    leaving_s: float = 0.0
    returning_s: float = 0.0
    out_of_bed: bool = False
    out_start: datetime | None = None
    out_s: float = 0.0
    zone: str | None = None
    pending_zone: str | None = None
    pending_s: float = 0.0
    transitions: int = 0
    bed_zone: str | None = None


class NocturnalMovementRule:
    """Night-window activity of a single occupant, in household-local time:
    more bed exits than `max_bed_exits`, out of bed longer than
    `out_of_bed_minutes` (time out of view -- e.g. in the bathroom -- is not
    counted), and wandering between zones. Each alert fires once per night
    (out-of-bed once per episode). Needs at least one bed zone; pauses while
    nobody or more than one person is confidently visible."""

    kind = EventKind.NOCTURNAL_MOVEMENT

    def __init__(self) -> None:
        self._night: _Night | None = None

    def reset(self) -> None:
        self._night = None

    def update(self, step: Step, settings: DetectionSettings) -> list[FallEvent]:
        cfg = settings.nocturnal
        beds = [z for z in settings.zones if z.kind is ZoneKind.BED]
        if not beds or not in_window(step.at, cfg.start, cfg.end, settings.timezone):
            self._night = None
            return []
        key = _night_key(step.at, cfg.start, cfg.end, settings.timezone)
        if self._night is None or self._night.key != key:
            self._night = _Night(key=key)
        night = self._night
        people = step.confident_people
        if len(people) != 1:
            return []  # nobody to follow, or several people: ambiguous, pause
        person, dt = people[0], step.dt
        zone = placed_zone(person.anchor, settings)
        in_bed = zone is not None and zone.kind is ZoneKind.BED
        zone_key = zone.zone_id if zone is not None else "-"
        events: list[FallEvent] = []

        if in_bed:
            night.in_bed_s += dt
            night.leaving_s = 0.0
            night.bed_zone = zone.zone_id
            if night.out_of_bed:
                night.returning_s += dt
                if night.returning_s >= RETURN_CONFIRM_S:
                    night.out_of_bed, night.out_start, night.out_s = False, None, 0.0
                    night.in_bed_s = night.returning_s
        else:
            night.returning_s = 0.0
            if not night.out_of_bed:
                night.leaving_s += dt
                if night.leaving_s >= EXIT_CONFIRM_S and night.in_bed_s >= BED_SETTLE_S:
                    night.out_of_bed, night.out_start = True, step.at
                    night.out_s, night.in_bed_s = night.leaving_s, 0.0
                    night.exits += 1
                    if night.exits > cfg.max_bed_exits and "exits" not in night.fired:
                        night.fired.add("exits")
                        events.append(make_event(
                            step, self.kind, Severity.WARNING, f"exits:{night.key}",
                            signals={"bed_exits": float(night.exits)}, zone_id=night.bed_zone))
            else:
                night.out_s += dt
                episode = f"out:{epoch_ms(night.out_start)}"
                if night.out_s >= cfg.out_of_bed_minutes * 60 and episode not in night.fired:
                    night.fired.add(episode)
                    events.append(make_event(step, self.kind, Severity.WARNING, episode,
                                             signals={"duration_s": round(night.out_s, 1)}))

        if night.out_of_bed:
            if zone_key == night.zone:
                night.pending_zone, night.pending_s = None, 0.0
            elif zone_key == night.pending_zone:
                night.pending_s += dt
            else:
                night.pending_zone, night.pending_s = zone_key, dt
            if night.pending_zone is not None and night.pending_s >= ZONE_SETTLE_S:
                night.zone, night.pending_zone, night.pending_s = night.pending_zone, None, 0.0
                night.transitions += 1
                if night.transitions >= WANDER_TRANSITIONS and "wander" not in night.fired:
                    night.fired.add("wander")
                    events.append(make_event(
                        step, self.kind, Severity.WARNING, f"wander:{night.key}",
                        signals={"transitions": float(night.transitions)}))
        else:
            night.zone, night.pending_zone, night.pending_s = zone_key, None, 0.0
        return events


def _night_key(at: datetime, start, end, tz: str) -> str:
    """The household-local date the night began on (22:00-05:00 at 02:00 on the
    24th belongs to the night of the 23rd)."""
    local = at.astimezone(ZoneInfo(tz))
    day = local.date()
    if start > end and local.time() < end:
        day -= timedelta(days=1)
    return day.isoformat()


# -- bathroom duration ---------------------------------------------------------------


@dataclass
class _Visit:
    start: datetime
    zone_id: str
    elapsed_s: float = 0.0
    fired: set[str] = field(default_factory=set)


class BathroomDurationRule:
    """A person seen entering a bathroom-door zone and then not seen again:
    the absence is timed from when they disappeared. Anyone reappearing in a
    bathroom-door zone ends it. The timer pauses while anyone else is visible
    (occupancy is ambiguous) and across camera outages. Warning at
    `warning_minutes`, critical at `critical_minutes`, once per visit.

    This measures a prolonged absence after entering the bathroom area; it
    never claims what happened there. Bathroom events are never recorded."""

    kind = EventKind.BATHROOM_DURATION

    def __init__(self) -> None:
        self._visit: _Visit | None = None

    def reset(self) -> None:
        self._visit = None

    def update(self, step: Step, settings: DetectionSettings) -> list[FallEvent]:
        doors = [z for z in settings.zones if z.kind is ZoneKind.BATHROOM_DOOR]
        if not doors:
            self._visit = None
            return []
        visit = self._visit
        if visit is not None:
            arrived = set(step.appeared) | set(step.reacquired)
            for person in step.people:
                if person.local_id in arrived and zone_at(*person.anchor, doors) is not None:
                    self._visit = None
                    return []
        if visit is None:
            if step.after_outage:
                return []
            for gone in step.lost:
                door = zone_at(*gone.anchor, doors)
                if gone.confident and door is not None:
                    self._visit = _Visit(start=step.at, zone_id=door.zone_id)
                    break
            return []
        if step.people:
            return []  # someone else is here: occupancy is ambiguous, pause
        visit.elapsed_s += step.dt
        cfg = settings.bathroom
        events = []
        for name, limit, severity in (("warning", cfg.warning_minutes, Severity.WARNING),
                                      ("critical", cfg.critical_minutes, Severity.CRITICAL)):
            if visit.elapsed_s >= limit * 60 and name not in visit.fired:
                visit.fired.add(name)
                events.append(make_event(
                    step, self.kind, severity, f"visit:{epoch_ms(visit.start)}",
                    signals={"duration_s": round(visit.elapsed_s, 1)}, zone_id=visit.zone_id))
        return events


def default_rules() -> list:
    """The three activity rules every agent (and server inference) runs."""
    return [ProlongedPositionRule(), NocturnalMovementRule(), BathroomDurationRule()]
