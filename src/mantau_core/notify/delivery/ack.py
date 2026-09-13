"""The far end of the latency chain: a human opened the alert.

This is what turns "under 5 seconds" from a claim measured to "FCM accepted
our HTTP call" into one measured to an actual person. It also cancels the
escalation walk — `on_first_ack` is how `escalation/policy.py` finds out to
stop pinging the next contact.
"""

from __future__ import annotations

import threading
from collections.abc import Callable


class AckService:
    def __init__(self) -> None:
        self._acked_by: dict[str, set[str]] = {}
        self._on_first_ack: dict[str, list[Callable[[str], None]]] = {}
        self._lock = threading.Lock()

    def on_first_ack(self, event_id: str, callback: Callable[[str], None]) -> None:
        """Register `callback(member_id)` to run once, the first time this
        event is acked. A no-op if the event was already acked when called —
        callers that need "already acked" as a fast-path should check
        `is_acked` themselves first."""
        with self._lock:
            self._on_first_ack.setdefault(event_id, []).append(callback)

    def ack(self, event_id: str, *, member_id: str) -> bool:
        """Record an ack. Returns True if this was the first ack for the event."""
        with self._lock:
            already_acked = bool(self._acked_by.get(event_id))
            self._acked_by.setdefault(event_id, set()).add(member_id)
            callbacks = [] if already_acked else self._on_first_ack.pop(event_id, [])
        for callback in callbacks:
            callback(member_id)
        return not already_acked

    def is_acked(self, event_id: str) -> bool:
        with self._lock:
            return bool(self._acked_by.get(event_id))

    def acked_by(self, event_id: str) -> set[str]:
        with self._lock:
            return set(self._acked_by.get(event_id, set()))
