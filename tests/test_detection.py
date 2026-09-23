"""NullDetector must satisfy the Detector protocol and only fire on cadence.
MediapipeDetector must fail loudly (not silently, not at import time) when
mantau-AI's streaming entrypoint is not installed.
"""

import sys

import numpy as np
import pytest

from mantau_core.detection import Detector, NullDetector
from mantau_core.detection.mediapipe_adapter import MediapipeDetector

FRAME = np.zeros((4, 4, 3), dtype=np.uint8)


def test_null_detector_satisfies_the_protocol():
    assert isinstance(NullDetector("cam-1"), Detector)


def test_null_detector_never_fires_by_default():
    det = NullDetector("cam-1")
    for ts in range(0, 1000, 33):
        assert det.push(FRAME, ts) == []
    det.close()


def test_null_detector_fires_on_a_fixed_cadence():
    det = NullDetector("cam-1", trigger_every_n_frames=3)
    fires = [det.push(FRAME, i) for i in range(9)]
    fired_at = [i for i, events in enumerate(fires) if events]
    assert fired_at == [2, 5, 8]  # 0-indexed frame count -> every 3rd push
    assert fires[2][0].camera_id == "cam-1"
    assert fires[2][0].confidence == 1.0


def test_mediapipe_adapter_fails_loudly_without_mantau_ai(monkeypatch):
    # Without the `detection` extra, constructing the adapter must say so
    # clearly, not raise a bare ImportError or (worse) silently do nothing.
    monkeypatch.setitem(sys.modules, "mantau.api.streaming", None)
    with pytest.raises(ImportError, match="streaming entrypoint"):
        MediapipeDetector("cam-1", config={})
