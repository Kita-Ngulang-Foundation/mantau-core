"""The activity rules against the golden scenario fixtures (shared with the
Android agent's Kotlin port), plus the behaviors the fixtures pin down."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

import pytest

from mantau_core.activity import (
    ActivityEngine, FrameObservation, PersonObservation, Posture, TrackingConfig,
    TrackRegistry, default_rules,
)
from mantau_core.contracts import DetectionSettings, Envelope, EventKind

FIXTURES = Path(str(resources.files("mantau_core.activity").joinpath(
    "fixtures/activity_sequences")))
FILES = sorted(FIXTURES.glob("*.json"))
ALLOWED_SIGNALS = {"duration_s", "movement", "confidence", "bed_exits", "transitions"}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _replay(fixture: dict, steps=None, engine: ActivityEngine | None = None):
    engine = engine or ActivityEngine(default_rules(),
                                      DetectionSettings.model_validate(fixture["settings"]))
    events = []
    for step in steps if steps is not None else fixture["steps"]:
        if step.get("camera_lost"):
            engine.camera_lost()
            continue
        people = tuple(PersonObservation(track_id=p[0], bbox=(p[1], p[2], p[3], p[4]),
                                         posture=Posture(p[5]), motion=p[6], confidence=p[7])
                       for p in step["people"])
        events += engine.update(FrameObservation(camera_id=fixture["camera_id"],
                                                 at=_at(step["at"]), people=people))
    return events


def _json(event) -> dict:
    return {
        "event_id": event.event_id, "kind": event.kind.value, "severity": event.severity.value,
        "occurred_at": event.occurred_at.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "confidence": event.confidence, "track_id": event.track_id, "zone_id": event.zone_id,
        "signals": event.signals,
    }


def _kinds(name: str) -> list[tuple[str, str]]:
    return [(e["kind"], e["severity"]) for e in _load(name)["expected"]]


def test_fixtures_exist():
    assert len(FILES) >= 20


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_replay_matches_the_golden_events(path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    assert [_json(e) for e in _replay(fixture)] == fixture["expected"]


# -- immobility vs sleep vs sitting ---------------------------------------------------

def test_lying_on_the_floor_warns_then_escalates():
    assert _kinds("floor_lying_warning_then_critical") == [
        ("stillness", "warning"), ("stillness", "critical")]
    first = _load("floor_lying_warning_then_critical")["expected"][0]
    assert first["signals"]["duration_s"] == pytest.approx(120, abs=1)


def test_sleep_and_sitting_are_rest():
    assert _kinds("sleeping_in_bed_is_rest") == []
    assert _kinds("sitting_on_sofa_is_rest") == []
    assert _kinds("immobile_at_night_is_rest") == []
    assert _kinds("immobile_elsewhere_by_day") == [("stillness", "warning"),
                                                   ("stillness", "critical")]
    assert _kinds("moving_resets_immobility") == []


def test_floor_zone_restricts_floor_and_is_reported():
    events = _load("floor_zone_restricts_floor")["expected"]
    assert [(e["kind"], e["zone_id"]) for e in events] == [("stillness", "floor")]


# -- people, occlusion, outages, clocks -------------------------------------------------

def test_visitors_and_excluded_zones():
    events = _load("visitor_does_not_mask_a_fall")["expected"]
    assert [(e["kind"], e["track_id"]) for e in events] == [("stillness", 1)]
    assert _kinds("excluded_zone_is_ignored") == []
    assert _kinds("night_two_people_is_ambiguous") == []


def test_occlusion_low_confidence_outage_and_regression_pause_instead_of_count():
    # Each lies on the floor for 120 counted seconds; the paused time is on top.
    expected = {
        "occlusion_pauses_and_keeps_the_track": 20,   # hidden
        "low_confidence_pauses": 90,                  # not trusted
        "camera_outage_pauses": 300,                  # camera down
    }
    for name, paused in expected.items():
        fixture = _load(name)
        start = _at(fixture["steps"][0]["at"])
        event = fixture["expected"][0]
        assert event["kind"] == "stillness" and event["severity"] == "warning", name
        assert (_at(event["occurred_at"]) - start).total_seconds() == pytest.approx(
            120 + paused, abs=2), name
    occlusion = _load("occlusion_pauses_and_keeps_the_track")["expected"][0]
    assert occlusion["track_id"] == 1  # the new detector track kept the local id
    regression = _load("clock_regression_pauses")["expected"]
    assert [(e["kind"], e["severity"]) for e in regression] == [("stillness", "warning")]


def test_registry_pauses_on_regression_gap_and_outage():
    registry = TrackRegistry(TrackingConfig(max_frame_gap_s=5))
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    obs = lambda t, *people: FrameObservation(camera_id="c", at=t, people=people)  # noqa: E731
    p = PersonObservation(track_id=1, bbox=(0.1, 0.1, 0.1, 0.3), confidence=0.9)
    assert registry.step(obs(t0, p)).dt == 0.0                         # first frame
    assert registry.step(obs(t0 + timedelta(seconds=1), p)).dt == 1.0
    assert registry.step(obs(t0 + timedelta(seconds=0.5), p)).dt == 0.0  # regression
    assert registry.step(obs(t0 + timedelta(seconds=1.5), p)).dt == 1.0  # re-based
    assert registry.step(obs(t0 + timedelta(seconds=30), p)).dt == 0.0   # gap
    registry.camera_lost()
    step = registry.step(obs(t0 + timedelta(seconds=31), p))
    assert step.dt == 0.0 and step.after_outage
    low = PersonObservation(track_id=1, bbox=(0.1, 0.1, 0.1, 0.3), confidence=0.2)
    assert not registry.step(obs(t0 + timedelta(seconds=32), low)).people[0].confident


def test_registry_ids_use_position_only():
    registry = TrackRegistry()
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    here = PersonObservation(track_id=1, bbox=(0.1, 0.1, 0.1, 0.3))
    near = PersonObservation(track_id=2, bbox=(0.12, 0.1, 0.1, 0.3))
    far = PersonObservation(track_id=3, bbox=(0.8, 0.1, 0.1, 0.3))
    first = registry.step(FrameObservation(camera_id="c", at=t0, people=(here,)))
    registry.step(FrameObservation(camera_id="c", at=t0 + timedelta(seconds=1)))
    back = registry.step(FrameObservation(camera_id="c", at=t0 + timedelta(seconds=2),
                                          people=(near, far)))
    assert back.people[0].local_id == first.people[0].local_id
    assert back.reacquired == (first.people[0].local_id,)
    assert back.people[1].local_id not in (first.people[0].local_id,)
    assert back.appeared == (back.people[1].local_id,)


# -- bathroom ----------------------------------------------------------------------------

def test_bathroom_absence_escalates_and_ends_on_return():
    events = _load("bathroom_warning_then_critical_then_return")["expected"]
    assert [(e["severity"], e["zone_id"]) for e in events] == [
        ("warning", "bathroom"), ("critical", "bathroom")]
    assert [e["signals"]["duration_s"] for e in events] == [1200.0, 2400.0]
    assert _kinds("bathroom_short_visit") == []


def test_bathroom_pauses_for_other_people_and_outages():
    assert _kinds("bathroom_visitor_pauses") == [("bathroom_duration", "warning")]
    assert _kinds("bathroom_outage_does_not_start_a_visit") == []
    assert _kinds("bathroom_outage_pauses_a_visit") == [("bathroom_duration", "warning")]


# -- night -----------------------------------------------------------------------------------

def test_night_routines():
    assert _kinds("night_single_bathroom_trip") == []
    exits = _load("night_repeated_bed_exits")["expected"]
    assert [e["signals"] for e in exits] == [{"bed_exits": 3.0}]
    assert _kinds("night_out_of_bed_too_long") == [("nocturnal_movement", "warning")]
    wander = _load("night_wandering")["expected"]
    assert [e["signals"] for e in wander] == [{"transitions": 8.0}]
    assert _kinds("daytime_bed_exits_are_not_nocturnal") == []


def test_dst_night_uses_local_window_and_real_durations():
    fixture = _load("dst_night_berlin")
    event = fixture["expected"][0]
    # Alert after the clocks jumped (03:xx CEST), 10 real minutes out of bed.
    assert _at(event["occurred_at"]) > datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)
    assert event["signals"]["duration_s"] == pytest.approx(600, abs=1)


# -- restart, duplicate delivery, privacy ----------------------------------------------------

def test_agent_restart_starts_clean_and_ids_are_deterministic():
    fixture = _load("floor_lying_warning_then_critical")
    steps = fixture["steps"]
    whole = [e.event_id for e in _replay(fixture)]
    assert whole == [e.event_id for e in _replay(fixture)]
    half = len(steps) // 2
    _replay(fixture, steps[:half])
    after_restart = _replay(fixture, steps[half:])
    # A restarted agent has no stale timer: it needs the full threshold again.
    assert len(after_restart) <= 1
    assert set(e.event_id for e in after_restart).isdisjoint(whole)


def test_duplicate_delivery_is_the_same_event():
    fixture = _load("bathroom_warning_then_critical_then_return")
    first, second = _replay(fixture), _replay(fixture)
    assert [e.event_id for e in first] == [e.event_id for e in second]
    envelope_a = Envelope.for_event("agent", 1, first[0])
    envelope_b = Envelope.for_event("agent", 1, second[0])
    assert envelope_a.payload == envelope_b.payload


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_payloads_are_privacy_safe(path):
    fixture = json.loads(path.read_text(encoding="utf-8"))
    zone_ids = {z["zone_id"] for z in fixture["settings"]["zones"]}
    for event in fixture["expected"]:
        assert set(event["signals"]) <= ALLOWED_SIGNALS
        assert event["zone_id"] is None or event["zone_id"] in zone_ids
        if event["kind"] == EventKind.BATHROOM_DURATION.value:
            assert set(event["signals"]) == {"duration_s"}
            assert event["track_id"] is None


def test_zone_id_is_left_out_of_fall_envelopes():
    from mantau_core.contracts import FallEvent
    fall = Envelope.for_event("agent", 1, FallEvent(camera_id="cam-1", confidence=0.9))
    assert "zone_id" not in fall.payload
    zoned = Envelope.for_event("agent", 2, FallEvent(camera_id="cam-1", zone_id="floor",
                                                     kind=EventKind.STILLNESS))
    assert zoned.payload["zone_id"] == "floor"
