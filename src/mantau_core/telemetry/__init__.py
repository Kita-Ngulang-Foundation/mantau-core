"""The number the whole project is judged on: captured -> delivered, under 5s.

Both backends stamp the same five stages through `LatencyTrace`, so
`mantau-testbed/scenarios/compare.py` can print one table instead of two
differently-measured ones. `metrics.py` is a tiny in-process counter/gauge
registry for everything else worth watching on a dashboard.
"""

from .latency import STAGES, LatencyTrace, Stage
from .metrics import Counter, Gauge, MetricsRegistry

__all__ = ["Stage", "STAGES", "LatencyTrace", "Counter", "Gauge", "MetricsRegistry"]
