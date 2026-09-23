"""THE ONLY module in mantau_core allowed to `import mantau.*` (the CV package).

Pulled in via the `detection` extra in pyproject.toml, which installs
`mantau` (github.com/Kita-Ngulang-Foundation/mantau-AI) from a pinned git SHA:

    pip install "mantau-core[detection]"

Bump that SHA deliberately, once mantau-AI's own tests are green -- never as
a side effect of an unrelated change here. Nothing outside this file may
import anything under `mantau.*` directly; if you find yourself doing that
elsewhere, the fix is to extend the translation below, not to add a second
import site.

`MediapipeDetector` wraps `mantau.api.streaming.StreamingDetector` (motion
gate, MediaPipe pose, rule-based fall confirmation, ONNX classifier) and
translates its output into this package's vocabulary: falls become
`contracts.FallEvent`, per-frame people become `activity` observations.
Every model file is verified against `artifacts.py`'s pinned SHA-256 before
any runtime sees it.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from mantau_core.activity.observations import (
    FrameObservation, Perception, PersonObservation, Posture,
)
from mantau_core.contracts import FallEvent, Severity

from .artifacts import BENCHMARK_FRAME, FALL_CLASSIFIER, FALL_CLASSIFIER_META, POSE_MODEL, verify

MODEL_DIR_ENV = "MANTAU_MODEL_DIR"


def _default_model_dir() -> Path:
    from mantau.api import streaming  # the only mantau.* import site (see module doc)
    return streaming.ASSETS_DIR


def replay_sequence(sequence: dict, model_dir: str | Path | None = None) -> tuple[dict, dict]:
    """Replay a recorded pose sequence (fixtures/pose_sequences) through
    mantau-AI's fall rules: (rules-only decisions, decisions with the verified
    ONNX classifier). Used to hold every agent to the same fixtures."""
    from mantau.api import sequences  # the only mantau.* import site (see module doc)
    from mantau.ml.classifier import load_classifier

    directory = Path(model_dir or os.environ.get(MODEL_DIR_ENV) or _default_model_dir())
    paths = verify(directory, (FALL_CLASSIFIER, FALL_CLASSIFIER_META))
    classifier = load_classifier(paths[FALL_CLASSIFIER])
    return sequences.replay(sequence), sequences.replay(sequence, classifier)


class MediapipeDetector:
    """Adapts mantau-AI's StreamingDetector to the `PerceivingDetector` protocol.

    `config` is passed through to StreamingDetector (same shape as mantau-AI's
    config/default.yaml sections), except that model paths always come from the
    verified model directory: `model_dir` argument, else `MANTAU_MODEL_DIR`,
    else the models packaged with the installed `mantau`.
    """

    def __init__(self, camera_id: str, config: dict | None = None, *,
                 model_dir: str | Path | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.camera_id = camera_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        try:
            from mantau.api.streaming import StreamingDetector  # the only mantau.* import
        except ImportError as exc:
            raise ImportError(
                "MediapipeDetector requires mantau-AI's streaming entrypoint "
                "(mantau.api.streaming.StreamingDetector). Install it with "
                '`pip install "mantau-core[detection]"`, or use '
                "mantau_core.detection.NullDetector."
            ) from exc
        directory = Path(model_dir or os.environ.get(MODEL_DIR_ENV) or _default_model_dir())
        classifier_cfg = dict(((config or {}).get("fall") or {}).get("classifier") or {})
        use_classifier = classifier_cfg.get("enabled", True)
        names = (POSE_MODEL, BENCHMARK_FRAME) + (
            (FALL_CLASSIFIER, FALL_CLASSIFIER_META) if use_classifier else ())
        self.artifacts = verify(directory, names)

        cfg = {key: dict(value) if isinstance(value, dict) else value
               for key, value in (config or {}).items()}
        cfg["pose"] = {**cfg.get("pose", {}), "model_path": str(self.artifacts[POSE_MODEL])}
        fall = dict(cfg.get("fall", {}))
        fall["classifier"] = {**classifier_cfg, "enabled": use_classifier}
        if use_classifier:
            fall["classifier"]["model_path"] = str(self.artifacts[FALL_CLASSIFIER])
        cfg["fall"] = fall
        cfg["stream"] = {**cfg.get("stream", {}),
                         "benchmark_frame": str(self.artifacts[BENCHMARK_FRAME])}
        self._impl = StreamingDetector(cfg)

    # -- Detector / PerceivingDetector ---------------------------------------
    def push(self, frame: np.ndarray, ts_ms: int) -> list[FallEvent]:
        return [self._translate(ev) for ev in self._impl.push(frame, ts_ms)]

    def perceive(self, frame: np.ndarray, ts_ms: int) -> Perception:
        result = self._impl.process(frame, ts_ms)
        events = [self._translate(ev) for ev in result.events]
        observation = None
        if result.people is not None:
            observation = FrameObservation(
                camera_id=self.camera_id, at=self._clock(),
                people=tuple(self._person(p) for p in result.people))
        return Perception(events=events, observation=observation)

    def benchmark(self, frames: int = 5) -> float:
        """Frames per second of pose + fall logic + classifier on this host.
        Raises if any model or runtime cannot load or run."""
        return float(self._impl.benchmark(frames))

    def close(self) -> None:
        self._impl.close()

    # -- translation -----------------------------------------------------------
    @staticmethod
    def _person(raw: Any) -> PersonObservation:
        return PersonObservation(
            track_id=int(raw.track_id),
            bbox=tuple(float(v) for v in raw.bbox),
            posture=Posture(getattr(raw.posture, "value", raw.posture)),
            motion=float(raw.motion),
            confidence=float(raw.confidence),
        )

    def _translate(self, raw: Any) -> FallEvent:
        """mantau-AI's FallEvent (a plain dataclass: track_id, timestamp_ms,
        confidence, velocity, aspect_ratio, torso_angle_deg) -> the contracts
        FallEvent every other module actually works with.

        `occurred_at` is wall-clock *now* rather than a translation of
        `raw.timestamp_ms` (stream-relative, not an absolute time) -- accurate
        because translation happens immediately after detection, in the same
        call.
        """
        signals = {
            name: float(value)
            for name, value in (
                ("velocity", getattr(raw, "velocity", None)),
                ("aspect_ratio", getattr(raw, "aspect_ratio", None)),
                ("torso_angle_deg", getattr(raw, "torso_angle_deg", None)),
            )
            if value is not None
        }
        return FallEvent(
            camera_id=self.camera_id,
            severity=Severity.CRITICAL,
            occurred_at=self._clock(),
            confidence=min(max(float(getattr(raw, "confidence", 0.0)), 0.0), 1.0),
            track_id=getattr(raw, "track_id", None),
            signals=signals,
        )
