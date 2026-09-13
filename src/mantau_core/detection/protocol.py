"""The interface both backends code against. Everything else is an implementation.

A `Detector` is deliberately synchronous and stateful per-camera: one
instance per camera stream, fed frames in order, holding whatever tracking
state it needs between calls. Callers run it off the event loop (a thread or
process) if the underlying implementation is CPU-bound — that's the caller's
concern, not this protocol's.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from mantau_core.contracts import FallEvent


@runtime_checkable
class Detector(Protocol):
    def push(self, frame: np.ndarray, ts_ms: int) -> list[FallEvent]:
        """Feed one BGR frame (H, W, 3) at `ts_ms` (monotonic, stream-relative).

        Returns zero or more newly-confirmed FallEvents this frame caused —
        most calls return an empty list. Never blocks on I/O.
        """
        ...

    def close(self) -> None:
        """Release any model/session resources. Idempotent."""
        ...
