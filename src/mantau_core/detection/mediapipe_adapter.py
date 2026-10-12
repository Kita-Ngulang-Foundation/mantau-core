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
The camera's bed and seating zones go the other way, into StreamingDetector's
`zones` setting (research: the confirm step's rest zones).
Every model file is verified against `artifacts.py`'s pinned SHA-256 before
any runtime sees it.
With `fall_model="research"` it instead wraps the final dense-window ensemble;
the server derives this setting from the camera's FallSettings.model.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import numpy as np

from mantau_core.activity.observations import (
    FrameObservation, Perception, PersonObservation, Posture,
)
from mantau_core.contracts import FallEvent, Severity, Zone

from .artifacts import BENCHMARK_FRAME, FALL_CLASSIFIER, FALL_CLASSIFIER_META, POSE_MODEL, RESEARCH_MODELS, verify

MODEL_DIR_ENV = "MANTAU_MODEL_DIR"
# Zone kinds StreamingDetector takes (mantau-AI `mantau.zones`). FLOOR zones
# stay here: core owns the found-on-the-floor path.
DETECTOR_ZONE_KINDS = ("bed", "seating")


def detector_zones(zones: Iterable[Zone | Mapping] | None) -> list[dict]:
    """The camera's zones as StreamingDetector's `zones` setting:
    `[{zone_id, kind, polygon: [{x, y}, ...]}]`, bed and seating only.
    Entries may be `Zone` objects or their JSON form."""
    out = []
    for zone in zones or ():
        if not isinstance(zone, Zone):
            zone = Zone.model_validate(zone)
        if zone.kind.value in DETECTOR_ZONE_KINDS:
            out.append({"zone_id": zone.zone_id, "kind": zone.kind.value,
                        "polygon": [{"x": p.x, "y": p.y} for p in zone.polygon]})
    return out


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
    else the models packaged with the installed `mantau`. `zones` (the
    camera's `DetectionSettings.zones`, else `config["zones"]`) reach the
    detector as bed and seating zones only; see `detector_zones`.
    """

    def __init__(self, camera_id: str, config: dict | None = None, *,
                 model_dir: str | Path | None = None,
                 clock: Callable[[], datetime] | None = None,
                 zones: Iterable[Zone | Mapping] | None = None) -> None:
        self.camera_id = camera_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._candidate_times = {}
        self._research = (config or {}).get("fall_model", "s1b") == "research"
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
        if self._research:
            from mantau.dense.streaming import DenseDetector
            self.artifacts = verify(directory, RESEARCH_MODELS + (BENCHMARK_FRAME,))
            # Bed and seating zones mark rest in the confirm step.
            settings = {**((config or {}).get("fall_confirmation") or {}),
                        "zones": detector_zones(zones if zones is not None else (config or {}).get("zones"))}
            self._impl = DenseDetector(settings, directory=directory)
            return
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
        cfg["zones"] = detector_zones(zones if zones is not None else cfg.get("zones"))
        self._impl = StreamingDetector(cfg)

    # -- Detector / PerceivingDetector ---------------------------------------
    def push(self, frame: np.ndarray, ts_ms: int) -> list[FallEvent]:
        if self._research:
            return self.perceive(frame, ts_ms).events
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

    def advance(self, ts_ms: int) -> list[FallEvent]:
        """Finish research candidates even if the camera stops sending frames."""
        return [self._translate(ev) for ev in self._impl.advance(ts_ms)] if self._research else []

    def cancel_candidates(self, ts_ms: int) -> list[FallEvent]:
        return [self._translate(ev) for ev in self._impl.rule.cancel(ts_ms / 1000)] if self._research else []

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
        if self._research:
            elapsed = (raw.resolved or raw.started) - raw.started
            at = self._candidate_times.setdefault(raw.event_id, self._clock() - timedelta(seconds=elapsed))
            signals = {"research_candidate": 1.0, "peak_p": raw.peak,
                       "down_fraction": raw.down_fraction, "tier": float(raw.tier),
                       "candidate_outcome": float(raw.outcome), "track_lost_down": float(raw.missing and raw.last_down),
                       "confirm_s": raw.deadline - raw.started, "confirmation_elapsed_s": elapsed,
                       "candidate_ts_ms": raw.started * 1000, "candidate_progress_s": raw.updated - raw.started,
                       "last_down": float(raw.last_down), "down_share_required": float(self._impl.rule.settings["down_share"]),
                       "rest_fraction": float(raw.rest_fraction), "in_rest_zone": float(raw.outcome == 5)}
            # Capture geometry remains available when the track disappears.
            for key, value in zip(("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"), raw.bbox):
                signals[key] = float(value)
            if raw.outcome:
                self._candidate_times.pop(raw.event_id, None)
            return FallEvent(event_id=raw.event_id, camera_id=self.camera_id,
                             occurred_at=at, track_id=raw.track_id, confidence=raw.peak,
                             severity=Severity.CRITICAL if raw.outcome == 1 else Severity.INFO,
                             signals=signals, zone_id=raw.zone_id if raw.outcome == 5 else None)
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
