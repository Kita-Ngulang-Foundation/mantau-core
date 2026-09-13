"""Per-(event, target) delivery history — in-process and short-lived on purpose.

Deliveries resolve in seconds; a backend that wants them to survive a
restart persists its own copy in SQLite (mirroring this shape) rather than
this module reaching for a database itself.
"""

from __future__ import annotations

import threading

from mantau_core.notify.protocol import Delivery, DeliveryStatus


class DeliveryTracker:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], list[Delivery]] = {}
        self._lock = threading.Lock()

    def record(self, delivery: Delivery, *, target: str) -> None:
        key = (delivery.event_id, target)
        with self._lock:
            self._records.setdefault(key, []).append(delivery)

    def latest(self, event_id: str, target: str) -> Delivery | None:
        with self._lock:
            history = self._records.get((event_id, target))
            return history[-1] if history else None

    def all_for_event(self, event_id: str) -> list[Delivery]:
        with self._lock:
            return [d for (eid, _tgt), hist in self._records.items() if eid == event_id for d in hist]

    def any_delivered(self, event_id: str) -> bool:
        return any(d.status is DeliveryStatus.DELIVERED for d in self.all_for_event(event_id))
