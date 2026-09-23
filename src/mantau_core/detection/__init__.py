"""Frames in, fall events out — the seam between "backend" and "computer vision."

`Detector` is the only thing either backend depends on. `NullDetector`
satisfies it in five lines, so backend wiring (workers, routes, the alert
path) can be built and tested today, before MediaPipe is installed and
before `mantau-ai` ships a streaming entrypoint. `MediapipeDetector` is the
ONLY place in this entire package that imports `mantau.*` — see its
docstring before touching it.
"""

from .null import NullDetector
from .protocol import Detector, PerceivingDetector

__all__ = ["Detector", "NullDetector", "PerceivingDetector"]
