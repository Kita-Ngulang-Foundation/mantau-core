"""Record the activity-rule golden fixtures.

Each scenario is a scripted sequence of observations (who is where, in what
posture, how confident) plus the household's DetectionSettings. The expected
events are what `ActivityEngine` with `default_rules()` produces for it. The
files are replayed by tests/test_activity_rules.py and by the Android agent's
Kotlin port, which must produce exactly the same events.

Usage:
    .venv\\Scripts\\python.exe scripts\\record_activity_fixtures.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mantau_core.activity import (  # noqa: E402
    ActivityEngine, FrameObservation, PersonObservation, Posture, default_rules,
)
from mantau_core.contracts import DetectionSettings  # noqa: E402

OUT = ROOT / "src" / "mantau_core" / "activity" / "fixtures" / "activity_sequences"
CAMERA = "cam-1"

# Zones (normalized). Bed on the left, sofa bottom-right, bathroom door top-right.
BED = {"zone_id": "bed", "kind": "bed", "name": "Tempat tidur", "polygon": [
    {"x": 0.05, "y": 0.45}, {"x": 0.40, "y": 0.45}, {"x": 0.40, "y": 0.80}, {"x": 0.05, "y": 0.80}]}
SOFA = {"zone_id": "sofa", "kind": "seating", "name": "Sofa", "polygon": [
    {"x": 0.60, "y": 0.70}, {"x": 0.95, "y": 0.70}, {"x": 0.95, "y": 0.98}, {"x": 0.60, "y": 0.98}]}
DOOR = {"zone_id": "bathroom", "kind": "bathroom_door", "name": "Pintu kamar mandi", "polygon": [
    {"x": 0.80, "y": 0.20}, {"x": 0.98, "y": 0.20}, {"x": 0.98, "y": 0.50}, {"x": 0.80, "y": 0.50}]}
FLOOR = {"zone_id": "floor", "kind": "floor", "name": "Lantai", "polygon": [
    {"x": 0.40, "y": 0.50}, {"x": 0.80, "y": 0.50}, {"x": 0.80, "y": 0.98}, {"x": 0.40, "y": 0.98}]}
TV = {"zone_id": "tv", "kind": "excluded", "name": "TV", "polygon": [
    {"x": 0.45, "y": 0.02}, {"x": 0.70, "y": 0.02}, {"x": 0.70, "y": 0.20}, {"x": 0.45, "y": 0.20}]}

# Anchor positions (bottom-centre of the box).
IN_BED, ON_SOFA, AT_DOOR, ON_FLOOR, MIDDLE = (0.2, 0.7), (0.75, 0.9), (0.9, 0.45), (0.5, 0.9), (0.55, 0.6)
ELSEWHERE = (0.3, 0.3)  # unzoned

# 02:00 and 13:00 in Jakarta (UTC+7).
NIGHT = datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc)
DAY = datetime(2026, 9, 24, 6, 0, tzinfo=timezone.utc)


def person(track: int, anchor, posture: str = "standing", motion: float = 0.0,
           confidence: float = 0.9) -> list:
    x, y = anchor
    return [track, round(x - 0.05, 4), round(y - 0.3, 4), 0.1, 0.3, posture, motion, confidence]


class Scene:
    def __init__(self, start: datetime, step_s: float = 1.0) -> None:
        self.at = start
        self.step = timedelta(seconds=step_s)
        self.steps: list[dict] = []

    def hold(self, seconds: float, *people) -> "Scene":
        for _ in range(int(round(seconds / self.step.total_seconds()))):
            self.steps.append({"at": _iso(self.at), "people": [list(p) for p in people]})
            self.at += self.step
        return self

    def camera_lost(self, seconds: float) -> "Scene":
        self.steps.append({"at": _iso(self.at), "camera_lost": True})
        self.at += timedelta(seconds=seconds)
        return self

    def jump(self, seconds: float) -> "Scene":
        """Move the clock without observations (a gap, or a regression if < 0)."""
        self.at += timedelta(seconds=seconds)
        return self


def _iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def replay(settings: dict, steps: list[dict]) -> list[dict]:
    engine = ActivityEngine(default_rules(), DetectionSettings.model_validate(settings))
    events = []
    for step in steps:
        at = datetime.fromisoformat(step["at"].replace("Z", "+00:00"))
        if step.get("camera_lost"):
            engine.camera_lost()
            continue
        people = tuple(PersonObservation(track_id=p[0], bbox=(p[1], p[2], p[3], p[4]),
                                         posture=Posture(p[5]), motion=p[6], confidence=p[7])
                       for p in step["people"])
        for event in engine.update(FrameObservation(camera_id=CAMERA, at=at, people=people)):
            events.append(event_json(event))
    return events


def event_json(event) -> dict:
    return {
        "event_id": event.event_id, "kind": event.kind.value, "severity": event.severity.value,
        "occurred_at": _iso(event.occurred_at), "confidence": event.confidence,
        "track_id": event.track_id, "zone_id": event.zone_id, "signals": event.signals,
    }


def settings(**changes) -> dict:
    base = DetectionSettings(zones=[BED, SOFA, DOOR, TV]).model_dump(mode="json")
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return DetectionSettings.model_validate(base).model_dump(mode="json")


def scenarios() -> list[tuple[str, str, dict, Scene]]:
    s = []
    lying = lambda t, where=ELSEWHERE, **k: person(t, where, "lying", **k)  # noqa: E731
    standing = lambda t, where=MIDDLE, **k: person(t, where, "standing", **k)  # noqa: E731

    s.append(("floor_lying_warning_then_critical",
              "Lying on the floor (no floor zone drawn: outside bed/seating counts) for 5 min "
              "with floor_minutes=2: warning at 2 min, critical at 4 min, once each.",
              settings(), Scene(DAY).hold(10, standing(1, ELSEWHERE)).hold(300, lying(1))))
    s.append(("floor_zone_restricts_floor",
              "With a floor zone drawn, lying outside it (and outside bed/seating) is not "
              "'on the floor'; lying inside it is.",
              settings(zones=[BED, SOFA, DOOR, FLOOR]),
              Scene(DAY).hold(150, lying(1, ELSEWHERE)).hold(150, lying(2, ON_FLOOR))))
    s.append(("sleeping_in_bed_is_rest",
              "Lying still in the bed zone for 20 minutes, day or night: no alert.",
              settings(), Scene(DAY, 2.0).hold(1200, lying(1, IN_BED))))
    s.append(("sitting_on_sofa_is_rest",
              "Sitting still on the sofa for 12 minutes with other_minutes=5: no alert.",
              settings(stillness={"other_minutes": 5}),
              Scene(DAY, 2.0).hold(720, person(1, ON_SOFA, "sitting"))))
    s.append(("immobile_elsewhere_by_day",
              "Standing without moving outside any zone for 11 minutes by day with "
              "other_minutes=5: warning at 5 min, critical at 10 min.",
              settings(stillness={"other_minutes": 5}),
              Scene(DAY, 2.0).hold(660, standing(1, ELSEWHERE, motion=0.001))))
    s.append(("immobile_at_night_is_rest",
              "The same immobility inside the night window: normal rest, no alert.",
              settings(stillness={"other_minutes": 5}),
              Scene(NIGHT, 2.0).hold(660, standing(1, ELSEWHERE, motion=0.001))))
    s.append(("moving_resets_immobility",
              "Moving more than the radius every 4 minutes keeps resetting the timer.",
              settings(stillness={"other_minutes": 5}),
              Scene(DAY, 2.0).hold(240, standing(1, (0.3, 0.3))).hold(240, standing(1, (0.3, 0.45)))
              .hold(240, standing(1, (0.3, 0.3)))))
    s.append(("occlusion_pauses_and_keeps_the_track",
              "Lying on the floor; after 60 s hidden for 20 s (lost), then found again under a new "
              "detector track id nearby: same local id, the hidden time is not counted.",
              settings(), Scene(DAY).hold(60, lying(1)).hold(20).hold(3, lying(7))
              .hold(120, lying(7))))
    s.append(("low_confidence_pauses",
              "Low landmark confidence for 90 s in the middle of lying on the floor: those "
              "seconds are not counted.",
              settings(), Scene(DAY).hold(60, lying(1)).hold(90, lying(1, confidence=0.2))
              .hold(120, lying(1))))
    s.append(("camera_outage_pauses",
              "Camera drops for 5 minutes while someone lies on the floor: the outage is not "
              "counted and does not trigger anything by itself.",
              settings(), Scene(DAY).hold(60, lying(1)).camera_lost(300).hold(90, lying(1))))
    s.append(("clock_regression_pauses",
              "The clock jumps back 10 minutes: that step counts nothing, later steps count "
              "from the new time.",
              settings(), Scene(DAY).hold(60, lying(1)).jump(-600).hold(80, lying(1))))
    s.append(("visitor_does_not_mask_a_fall",
              "Someone lies on the floor while a visitor walks around: each person is timed "
              "separately; the moving visitor raises nothing.",
              settings(),
              Scene(DAY).hold(200, lying(1), standing(2, MIDDLE, motion=0.01))))
    s.append(("excluded_zone_is_ignored",
              "A person-shaped figure on the TV (excluded zone) is never tracked.",
              settings(), Scene(DAY).hold(300, lying(1, (0.55, 0.15)))))

    s.append(("bathroom_warning_then_critical_then_return",
              "Walks into the bathroom door zone and disappears; 45 min later reappears at the "
              "door. warning_minutes=20, critical_minutes=40.",
              settings(), Scene(DAY, 5.0).hold(20, standing(1, MIDDLE)).hold(10, standing(1, AT_DOOR))
              .hold(2700).hold(20, standing(4, AT_DOOR)).hold(60, standing(4, MIDDLE))))
    s.append(("bathroom_short_visit",
              "A 10 minute bathroom visit: no alert.",
              settings(), Scene(DAY, 5.0).hold(10, standing(1, AT_DOOR)).hold(600)
              .hold(20, standing(2, AT_DOOR))))
    s.append(("bathroom_visitor_pauses",
              "While someone else is in the room the absence is ambiguous: the timer pauses "
              "for the 15 minutes the visitor is there, so the warning comes 15 minutes later.",
              settings(), Scene(DAY, 5.0).hold(10, standing(1, AT_DOOR)).hold(600)
              .hold(900, person(2, ON_SOFA, "sitting")).hold(900)))
    s.append(("bathroom_outage_does_not_start_a_visit",
              "Someone near the door when the camera drops for 30 minutes: an outage is not a "
              "disappearance into the bathroom.",
              settings(), Scene(DAY, 5.0).hold(10, standing(1, AT_DOOR)).camera_lost(1800)
              .hold(1800)))
    s.append(("bathroom_outage_pauses_a_visit",
              "A visit in progress is paused (not counted) during a 30 minute outage.",
              settings(), Scene(DAY, 5.0).hold(10, standing(1, AT_DOOR)).hold(600)
              .camera_lost(1800).hold(900)))

    night = settings(nocturnal={"max_bed_exits": 2, "out_of_bed_minutes": 10})
    s.append(("night_single_bathroom_trip",
              "At night: in bed, one trip to the bathroom (6 minutes out of view), back to bed. "
              "Normal: no alert.",
              night, Scene(NIGHT).hold(120, lying(1, IN_BED)).hold(30, standing(1, MIDDLE))
              .hold(10, standing(1, AT_DOOR)).hold(360).hold(10, standing(2, AT_DOOR))
              .hold(30, standing(2, MIDDLE)).hold(300, lying(2, IN_BED))))
    exits = Scene(NIGHT)
    for _ in range(3):
        exits.hold(90, lying(1, IN_BED)).hold(40, standing(1, MIDDLE))
    exits.hold(90, lying(1, IN_BED))
    s.append(("night_repeated_bed_exits",
              "Three bed exits in one night with max_bed_exits=2: one alert on the third.",
              night, exits))
    s.append(("night_out_of_bed_too_long",
              "Out of bed and in view for 12 minutes with out_of_bed_minutes=10: one alert.",
              night, Scene(NIGHT).hold(120, lying(1, IN_BED)).hold(720, standing(1, MIDDLE))))
    wander = Scene(NIGHT).hold(120, lying(1, IN_BED))
    for _ in range(5):
        wander.hold(10, standing(1, MIDDLE)).hold(10, person(1, ON_SOFA, "sitting"))
    s.append(("night_wandering",
              "Out of bed moving back and forth between the room and the sofa: wandering alert "
              "at the 8th zone change.", night, wander))
    s.append(("daytime_bed_exits_are_not_nocturnal",
              "The same three bed exits by day: no nocturnal alert.",
              night, Scene(DAY).hold(90, lying(1, IN_BED)).hold(40, standing(1, MIDDLE))
              .hold(90, lying(1, IN_BED)).hold(40, standing(1, MIDDLE))
              .hold(90, lying(1, IN_BED)).hold(40, standing(1, MIDDLE))))
    s.append(("night_two_people_is_ambiguous",
              "Two people moving at night (a carer): nocturnal timers pause.",
              night, Scene(NIGHT).hold(120, lying(1, IN_BED))
              .hold(720, standing(1, MIDDLE), standing(2, ELSEWHERE))))
    # Berlin switches to summer time at 02:00 local on 2026-03-29.
    dst = Scene(datetime(2026, 3, 29, 0, 52, tzinfo=timezone.utc))  # 01:52 CET; clocks jump 02:00 -> 03:00
    dst.hold(120, lying(1, IN_BED)).hold(840, standing(1, MIDDLE))
    s.append(("dst_night_berlin",
              "Europe/Berlin across the spring-forward change: the night window uses local "
              "time, durations use real elapsed time (14 min out of bed alerts once at 10).",
              settings(timezone="Europe/Berlin",
                       nocturnal={"max_bed_exits": 2, "out_of_bed_minutes": 10}), dst))
    return s


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for name, notes, cfg, scene in scenarios():
        fixture = {"schema_version": 1, "name": name, "notes": notes, "camera_id": CAMERA,
                   "settings": cfg, "steps": scene.steps}
        fixture["expected"] = replay(cfg, scene.steps)
        path = OUT / f"{name}.json"
        path.write_bytes((json.dumps(fixture, separators=(",", ":")) + "\n").encode("utf-8"))
        summary = [(e["kind"], e["severity"], e["occurred_at"][11:19]) for e in fixture["expected"]]
        print(f"{name}: {len(scene.steps)} steps, {path.stat().st_size // 1024} KiB -> {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
