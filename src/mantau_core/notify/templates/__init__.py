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
    signals = event.signals
    if event.kind is EventKind.NOCTURNAL_MOVEMENT:
        if signals.get("summary") == 1.0:
            return id_id.night_summary_text(
                camera_name=camera_name, bed_exits=round(signals.get("bed_exits", 0.0)),
                away_total_s=signals.get("away_total_s"),
                away_longest_s=signals.get("away_longest_s"),
                first_exit_min=signals.get("first_exit_min"))
        # Only the first-exit alert has exactly one exit: the "too many exits"
        # alert needs more than max_bed_exits, which is at least 1.
        if signals.get("bed_exits") == 1.0:
            return id_id.first_bed_exit_text(camera_name=camera_name)
    return id_id.anomaly_alert_text(
        camera_name=camera_name, kind=event.kind,
        duration_s=event.signals.get("duration_s"),
        on_floor=event.signals.get("floor") == 1.0,
    )


__all__ = ["render", "id_id"]
