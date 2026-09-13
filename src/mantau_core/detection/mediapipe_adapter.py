"""THE ONLY module in mantau_core allowed to `import mantau.*` (the CV package).

Pulled in via the `detection` extra in pyproject.toml, which installs
`mantau` from a pinned git SHA:

    pip install "mantau-core[detection]"

Bump that SHA deliberately, once mantau-ai's own tests are green — never as
a side effect of an unrelated change here. Nothing outside this file may
import anything under `mantau.*` directly; if you find yourself doing that
elsewhere, the fix is to extend the translation below, not to add a second
import site.

Requires mantau-ai's streaming entrypoint (`mantau.api.streaming.StreamingDetector`
— frames in, `mantau.stages.fall.FallEvent`-shaped objects out), which does
not exist in the currently checked-out mantau-ai revision. Until it ships,
constructing this class raises a clear, actionable ImportError; use
`mantau_core.detection.NullDetector` in the meantime — nothing else in either
backend needs to change when this adapter is later swapped in.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from mantau_core.contracts import FallEvent, Severity


class MediapipeDetector:
    """Adapts mantau-ai's StreamingDetector to the mantau_core `Detector` protocol."""

    def __init__(self, camera_id: str, config: dict) -> None:
        self.camera_id = camera_id
        try:
            from mantau.api.streaming import StreamingDetector  # the only mantau.* import
        except ImportError as exc:
            raise ImportError(
                "MediapipeDetector requires mantau-ai's streaming entrypoint "
                "(mantau.api.streaming.StreamingDetector), which isn't in the "
                "checked-out mantau-ai revision yet. Install it once that lands "
                '(`pip install "mantau-core[detection]"`), or use '
                "mantau_core.detection.NullDetector until then."
            ) from exc
        self._impl = StreamingDetector(config)

    def push(self, frame: np.ndarray, ts_ms: int) -> list[FallEvent]:
        raw_events = self._impl.push(frame, ts_ms)
        return [self._translate(ev) for ev in raw_events]

    def _translate(self, raw: Any) -> FallEvent:
        """mantau-ai's FallEvent (a plain dataclass: track_id, timestamp_ms,
        confidence, velocity, aspect_ratio, torso_angle_deg) -> the contracts
        FallEvent every other module actually works with.

        `occurred_at` defaults to wall-clock *now* rather than translating
        `raw.timestamp_ms` (stream-relative, not an absolute time) — accurate
        enough given translation happens immediately after detection, on the
        same process, on every call.
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
            confidence=float(getattr(raw, "confidence", 0.0)),
            track_id=getattr(raw, "track_id", None),
            signals=signals,
        )

    def close(self) -> None:
        self._impl.close()
