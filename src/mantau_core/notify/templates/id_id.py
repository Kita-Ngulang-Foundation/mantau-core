"""Bahasa Indonesia alert copy — the only locale for the MVP. Tone matches
the existing app copy (see mantau-app's `demo_data.dart` FallEvent strings).
"""

from __future__ import annotations

from mantau_core.contracts import EventKind

_ANOMALY_LABELS: dict[EventKind, str] = {
    EventKind.STILLNESS: "diam berkepanjangan",
    EventKind.NOCTURNAL_MOVEMENT: "gerakan di malam hari",
    EventKind.BATHROOM_DURATION: "durasi lama di kamar mandi",
}


def fall_alert_text(*, camera_name: str, confidence: float) -> tuple[str, str]:
    pct = round(confidence * 100)
    title = f"Jatuh terdeteksi — {camera_name}"
    body = (
        f"Sistem mendeteksi kemungkinan jatuh di {camera_name} "
        f"(keyakinan {pct}%). Ketuk untuk meninjau rekaman."
    )
    return title, body


def anomaly_alert_text(*, camera_name: str, kind: EventKind) -> tuple[str, str]:
    label = _ANOMALY_LABELS.get(kind, "aktivitas tidak biasa")
    title = f"Peringatan — {camera_name}"
    body = f"Sistem mendeteksi {label} di {camera_name}. Ketuk untuk meninjau."
    return title, body


def escalation_text(*, camera_name: str, unresponsive_contact_name: str) -> tuple[str, str]:
    """Sent to the NEXT contact in the chain, naming who already missed it."""
    title = f"Belum direspons — {camera_name}"
    body = (
        f"{unresponsive_contact_name} belum menanggapi peringatan jatuh di "
        f"{camera_name}. Mohon segera periksa."
    )
    return title, body
