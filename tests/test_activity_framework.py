from datetime import datetime, time, timezone

import pytest
from pydantic import ValidationError

from mantau_core.activity import (
    ActivityEngine, FrameObservation, PersonObservation, Posture, in_window, zone_at,
)
from mantau_core.contracts import (
    CommandType, DetectionSettings, EventKind, FallEvent, Point, Zone, ZoneKind,
)

SQUARE = [Point(x=0.1, y=0.1), Point(x=0.5, y=0.1), Point(x=0.5, y=0.5), Point(x=0.1, y=0.5)]
AT = datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc)  # 02:00 in Jakarta


def _person(x=0.3, y=0.3, posture=Posture.STANDING):
    # bbox anchored so the bottom-center lands on (x, y)
    return PersonObservation(track_id=1, bbox=(x - 0.05, y - 0.2, 0.1, 0.2), posture=posture)


class _Recorder:
    kind = EventKind.STILLNESS

    def __init__(self):
        self.seen = []
        self.resets = 0

    def update(self, step, settings):
        self.seen.append(step)
        return [FallEvent(camera_id=step.camera_id, kind=self.kind)]

    def reset(self):
        self.resets += 1


class _Broken:
    kind = EventKind.BATHROOM_DURATION

    def update(self, step, settings):
        raise RuntimeError("boom")

    def reset(self):
        pass


def test_defaults_are_safe_and_complete():
    settings = DetectionSettings()
    assert settings.timezone == "Asia/Jakarta"
    assert settings.stillness.floor_minutes == 2.0
    assert settings.nocturnal.start == time(22, 0)
    assert settings.bathroom.critical_minutes >= settings.bathroom.warning_minutes
    assert DetectionSettings.model_validate_json(settings.model_dump_json()) == settings


@pytest.mark.parametrize("bad", [
    {"timezone": "Mars/Olympus"},
    {"zones": [{"zone_id": "a", "kind": "bed", "polygon": [{"x": 0, "y": 0}] * 2}]},
    {"zones": [{"zone_id": "a", "kind": "bed", "polygon": [{"x": 2, "y": 0}] * 3}]},
    {"zones": [{"zone_id": "a", "kind": "bed", "polygon": [{"x": 0, "y": 0}] * 3},
               {"zone_id": "a", "kind": "floor", "polygon": [{"x": 0, "y": 0}] * 3}]},
    {"bathroom": {"warning_minutes": 30, "critical_minutes": 10}},
    {"unexpected": True},
])
def test_invalid_settings_are_rejected(bad):
    with pytest.raises(ValidationError):
        DetectionSettings.model_validate(bad)


def test_zone_lookup_uses_the_floor_anchor():
    zones = [Zone(zone_id="bed", kind=ZoneKind.BED, polygon=SQUARE)]
    assert zone_at(0.3, 0.3, zones).zone_id == "bed"
    assert zone_at(0.7, 0.3, zones) is None
    assert zone_at(0.3, 0.3, zones, kinds=[ZoneKind.FLOOR]) is None
    person = _person(0.3, 0.45)
    assert zone_at(*person.anchor, zones).zone_id == "bed"


def test_night_window_wraps_midnight_in_household_time():
    assert in_window(AT, time(22), time(5), "Asia/Jakarta")
    assert not in_window(AT.replace(hour=5), time(22), time(5), "Asia/Jakarta")  # 12:00 WIB
    with pytest.raises(ValueError):
        in_window(AT.replace(tzinfo=None), time(22), time(5), "Asia/Jakarta")


def test_engine_runs_enabled_rules_and_isolates_failures():
    recorder, broken = _Recorder(), _Broken()
    engine = ActivityEngine([recorder, broken])
    events = engine.update(FrameObservation(camera_id="cam-1", at=AT, people=(_person(),)))
    assert [e.kind for e in events] == [EventKind.STILLNESS]
    assert engine.failures == {"_Broken": 1}

    engine.apply_settings(DetectionSettings(version=2, stillness={"enabled": False}))
    assert recorder.resets == 1
    assert engine.update(FrameObservation(camera_id="cam-1", at=AT)) == []


def test_people_in_excluded_zones_are_ignored():
    recorder = _Recorder()
    engine = ActivityEngine([recorder], DetectionSettings(zones=[
        Zone(zone_id="tv", kind=ZoneKind.EXCLUDED, polygon=SQUARE)]))
    engine.update(FrameObservation(camera_id="cam-1", at=AT,
                                   people=(_person(0.3, 0.3), _person(0.8, 0.9))))
    assert [p.anchor for p in recorder.seen[0].people] == [pytest.approx((0.8, 0.9))]


def test_bow_tie_and_sliver_zones_are_rejected():
    bow_tie = [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.5, "y": 0.1},
               {"x": 0.1, "y": 0.5}]
    sliver = [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.5, "y": 0.1001}]
    repeated = [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.5, "y": 0.1},
                {"x": 0.1, "y": 0.5}]
    for polygon, reason in ((bow_tie, "cross"), (sliver, "area"), (repeated, "repeats")):
        with pytest.raises(ValidationError, match=reason):
            Zone(zone_id="z", kind=ZoneKind.FLOOR, polygon=polygon)
    concave = [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9},
               {"x": 0.5, "y": 0.4}, {"x": 0.1, "y": 0.9}]
    assert Zone(zone_id="z", kind=ZoneKind.FLOOR, polygon=concave)


def test_settings_command_type_is_part_of_control_v1():
    assert CommandType("apply_detection_settings") is CommandType.APPLY_DETECTION_SETTINGS
