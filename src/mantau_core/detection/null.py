"""A Detector that does nothing — until you ask it to.

Default behavior is "never fires," which is what backend wiring needs: prove
frames flow from source to worker to (no) alert without MediaPipe installed.
Setting `trigger_every_n_frames` makes it synthesize a FallEvent on a fixed
cadence instead, which is the fastest way to exercise the *entire* alert
path — fanout, push, ack, escalation — before real detection exists at all.
"""

from __future__ import annotations

import numpy as np

from mantau_core.contracts import FallEvent


class NullDetector:
    def __init__(self, camera_id: str, *, trigger_every_n_frames: int | None = None) -> None:
        self.camera_id = camera_id
        self._trigger_every = trigger_every_n_frames
        self._frame_count = 0

    def push(self, frame: np.ndarray, ts_ms: int) -> list[FallEvent]:
        self._frame_count += 1
        if self._trigger_every and self._frame_count % self._trigger_every == 0:
            return [FallEvent(
                camera_id=self.camera_id,
                confidence=1.0,
                signals={"synthetic": 1.0},
            )]
        return []

    def close(self) -> None:
        pass
