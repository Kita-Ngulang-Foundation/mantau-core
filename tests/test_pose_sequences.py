"""Recorded pose sequences: the fixtures every agent's fall logic is held to.

Schema checks run everywhere. With the `detection` extra installed, each
sequence is replayed through mantau-AI's fall rules and must reproduce its
recorded decisions; the scenario tests pin what those decisions are
(regression coverage for fall, slow lie-down, squat, occlusion, reconnect).
The Android agent's unit tests replay the same files through the Kotlin port.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest

from mantau_core.detection import artifacts

SEQUENCES = Path(str(resources.files("mantau_core.detection").joinpath(
    "fixtures/pose_sequences")))
FILES = sorted(SEQUENCES.glob("*.json"))


def _load(name: str) -> dict:
    return json.loads((SEQUENCES / f"{name}.json").read_text(encoding="utf-8"))


def _events(name: str, key: str = "with_classifier") -> list[int]:
    return [e["timestamp_ms"] for e in _load(name)["expected"][key]["events"]]


def test_fixtures_exist():
    assert len(FILES) >= 8


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_schema(path):
    seq = json.loads(path.read_text(encoding="utf-8"))
    assert seq["schema_version"] == 1
    h, w = seq["image_shape"]
    assert h > 0 and w > 0
    assert seq["classifier"]["sha256"] == artifacts.manifest()[artifacts.FALL_CLASSIFIER].sha256
    times = [f["t"] for f in seq["frames"]]
    assert times == sorted(set(times)), "timestamps strictly increase"
    for frame in seq["frames"]:
        for person in frame["people"]:
            assert len(person["lm"]) == 33 and all(len(p) == 3 for p in person["lm"])
            assert len(person["world"]) == 33 and all(len(p) == 3 for p in person["world"])
    for key in ("rules_only", "with_classifier"):
        assert len(seq["expected"][key]["states"]) == len(seq["frames"])


# -- scenario regression (decisions recorded from real clips) ---------------------

def test_fall_fires_exactly_once():
    assert len(_events("fall_ybclass_video1")) == 1
    assert len(_events("fall_urfall_02")) == 1


def test_walking_does_not_fire():
    assert _events("walk_ybclass_video5") == []


def test_slow_lie_down_does_not_fire():
    assert _events("slow_liedown_urfall_adl") == []
    assert _events("slow_liedown_urfall_adl", "rules_only") == []


def test_squat_does_not_fire():
    assert _events("squat_urfall_adl") == []


def test_occluded_legs_still_fire():
    """Lower 35% of the frame hidden: the fall is still confirmed once."""
    assert len(_events("occluded_fall_ybclass_video1")) == 1


def test_reconnect_gap_then_fall_fires_once_after_the_gap():
    seq = _load("reconnect_walk_then_fall")
    times = [f["t"] for f in seq["frames"]]
    gap_end = next(b for a, b in zip(times, times[1:]) if b - a > 10_000)
    events = _events("reconnect_walk_then_fall")
    assert len(events) == 1 and events[0] >= gap_end


def test_known_limitations_are_recorded_not_hidden():
    # 10 fps breaks track continuity during a fast fall (see fixture notes).
    assert _events("fall_ybclass_video3_10fps") == []
    # Lying down on a sofa is confirmed as a fall by the current rules + classifier.
    assert len(_events("liedown_sofa_urfall_adl11")) == 1


# -- replay against the Python implementation ---------------------------------------

@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_python_replay_reproduces_recorded_decisions(path):
    pytest.importorskip("mantau.api.sequences")
    from mantau_core.detection.mediapipe_adapter import replay_sequence
    seq = json.loads(path.read_text(encoding="utf-8"))
    rules, with_classifier = replay_sequence(seq)
    assert rules == seq["expected"]["rules_only"]
    assert with_classifier == seq["expected"]["with_classifier"]
