"""Household-local time for night windows."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo


def local_time(at: datetime, timezone: str) -> time:
    if at.tzinfo is None:
        raise ValueError("observation times must be timezone-aware")
    return at.astimezone(ZoneInfo(timezone)).time()


def in_window(at: datetime, start: time, end: time, timezone: str) -> bool:
    """True inside [start, end) in the household timezone; a window that
    passes midnight (22:00-05:00) wraps."""
    now = local_time(at, timezone)
    if start <= end:
        return start <= now < end
    return now >= start or now < end
