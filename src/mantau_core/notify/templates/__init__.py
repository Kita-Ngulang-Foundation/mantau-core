"""One locale today (`id_id`); `render()` is the seam for adding another
without callers caring which copy module actually ran.
"""

from __future__ import annotations

from mantau_core.contracts import EventKind, FallEvent

from . import id_id


def render(event: FallEvent, *, camera_name: str) -> tuple[str, str]:
    """(title, body) for a push/Telegram alert, in Bahasa Indonesia."""
    if event.kind is EventKind.FALL:
        return id_id.fall_alert_text(camera_name=camera_name, confidence=event.confidence)
    return id_id.anomaly_alert_text(camera_name=camera_name, kind=event.kind)


__all__ = ["render", "id_id"]
