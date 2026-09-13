"""A minimal, stdlib-only counter/gauge registry for a /health or /metrics route.

Deliberately not prometheus_client — that's a real option later, but a
weekend backend needs "how many events fired, how many pushes failed" on a
JSON endpoint, not a Prometheus exposition format.
"""

from __future__ import annotations

import threading


class Counter:
    """Monotonically increasing — event counts, error counts."""

    def __init__(self) -> None:
        self._value = 0.0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        return self._value


class Gauge:
    """Goes up and down — spool depth, active camera connections."""

    def __init__(self) -> None:
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        return self._value


class MetricsRegistry:
    """Named counters/gauges, created on first access, snapshottable as one dict."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._lock = threading.Lock()

    def counter(self, name: str) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter()
            return self._counters[name]

    def gauge(self, name: str) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge()
            return self._gauges[name]

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            out = {f"counter.{k}": c.value for k, c in self._counters.items()}
            out.update({f"gauge.{k}": g.value for k, g in self._gauges.items()})
            return out
