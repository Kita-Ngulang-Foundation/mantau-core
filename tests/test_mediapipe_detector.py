"""MediapipeDetector against the real mantau-AI package (the `detection` extra).

Skipped when mantau is not installed. Clip-based tests also need the
Y-B-Class clips on disk (MANTAU_TEST_CLIPS, default: the sibling mantau-AI
checkout's data/falls), which are not committed anywhere.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mantau.api.streaming")
cv2 = pytest.importorskip("cv2")

from mantau_core.activity import FrameObservation, Posture  # noqa: E402
from mantau_core.contracts import EventKind, FallEvent, Severity  # noqa: E402
from mantau_core.detection import Detector, PerceivingDetector  # noqa: E402
from mantau_core.detection.artifacts import ArtifactError, verify  # noqa: E402
from mantau_core.detection.mediapipe_adapter import (  # noqa: E402
    MediapipeDetector, _default_model_dir,
)

CLIPS = Path(os.environ.get(
    "MANTAU_TEST_CLIPS", Path(__file__).resolve().parents[2] / "mantau-AI" / "data" / "falls"))
NOW = datetime(2026, 9, 23, 7, 0, tzinfo=timezone.utc)


def _clip(name: str) -> Path:
    path = CLIPS / name
    if not path.exists():
        pytest.skip(f"{path} not present")
    return path


def _frames(path: Path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    i = 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        yield image, int(round(i * 1000.0 / fps))
        i += 1
    cap.release()


@pytest.fixture
def detector():
    det = MediapipeDetector("cam-1", clock=lambda: NOW)
    yield det
    det.close()


def test_packaged_models_match_the_pinned_manifest():
    verified = verify(_default_model_dir())
    assert len(verified) == 4


def test_satisfies_both_protocols(detector):
    assert isinstance(detector, Detector)
    assert isinstance(detector, PerceivingDetector)


def test_tampered_model_is_never_loaded(tmp_path):
    for path in _default_model_dir().iterdir():
        shutil.copy(path, tmp_path / path.name)
    task = tmp_path / "pose_landmarker_lite.task"
    data = bytearray(task.read_bytes())
    data[1000] ^= 0xFF
    task.write_bytes(bytes(data))
    with pytest.raises(ArtifactError, match="pose_landmarker_lite.task"):
        MediapipeDetector("cam-1", model_dir=tmp_path)


def test_model_dir_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MANTAU_MODEL_DIR", str(tmp_path))
    with pytest.raises(ArtifactError, match="not found"):
        MediapipeDetector("cam-1")


def test_fall_clip_becomes_one_contract_event(detector):
    events = []
    for image, ts in _frames(_clip("video_1.mp4")):
        events += detector.perceive(image, ts).events
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, FallEvent)
    assert event.kind is EventKind.FALL and event.severity is Severity.CRITICAL
    assert event.camera_id == "cam-1" and event.occurred_at == NOW
    assert 0.0 < event.confidence <= 1.0
    assert set(event.signals) == {"velocity", "aspect_ratio", "torso_angle_deg"}


def test_push_and_perceive_agree_on_falls():
    push_det = MediapipeDetector("cam-1", clock=lambda: NOW)
    perceive_det = MediapipeDetector("cam-1", clock=lambda: NOW)
    try:
        pushed, perceived = [], []
        for image, ts in _frames(_clip("video_1.mp4")):
            pushed += [(e.track_id, e.confidence) for e in push_det.push(image, ts)]
            perceived += [(e.track_id, e.confidence)
                          for e in perceive_det.perceive(image, ts).events]
    finally:
        push_det.close()
        perceive_det.close()
    assert pushed == perceived and len(pushed) == 1


def test_observations_use_activity_types(detector):
    observations = []
    for image, ts in _frames(_clip("video_1.mp4")):
        perception = detector.perceive(image, ts)
        if perception.observation is not None:
            observations.append(perception.observation)
    assert observations
    people = [p for o in observations for p in o.people]
    assert all(isinstance(o, FrameObservation) and o.camera_id == "cam-1" for o in observations)
    assert {p.posture for p in people} <= set(Posture)
    assert Posture.LYING in {p.posture for p in people}
    assert all(0.0 <= v <= 1.0 for p in people for v in p.bbox)


def test_walking_clip_never_fires(detector):
    for image, ts in _frames(_clip("video_5.mp4")):
        assert detector.perceive(image, ts).events == []


def test_empty_room_reports_no_people_and_no_falls(detector):
    rng = np.random.default_rng(3)
    room = np.full((240, 320, 3), 120, dtype=np.uint8)
    for i in range(150):
        frame = np.clip(room.astype(np.int16) + rng.integers(-3, 4, room.shape), 0, 255)
        perception = detector.perceive(frame.astype(np.uint8), i * 100)
        assert perception.events == []
        assert perception.observation is None or perception.observation.people == ()


def test_benchmark_measures_real_inference(detector):
    assert detector.benchmark(frames=2) > 0


def test_classifier_can_be_disabled_and_is_then_not_required(tmp_path):
    for name in ("pose_landmarker_lite.task", "benchmark_person.jpg"):
        shutil.copy(_default_model_dir() / name, tmp_path)
    det = MediapipeDetector("cam-1", {"fall": {"classifier": {"enabled": False}}},
                            model_dir=tmp_path)
    try:
        assert "fall_classifier.onnx" not in det.artifacts
    finally:
        det.close()
