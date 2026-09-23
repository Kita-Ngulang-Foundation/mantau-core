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


_ANOMALY_TITLES: dict[EventKind, str] = {
    EventKind.STILLNESS: "Tidak bergerak terlalu lama",
    EventKind.NOCTURNAL_MOVEMENT: "Aktivitas malam tidak biasa",
    EventKind.BATHROOM_DURATION: "Terlalu lama di kamar mandi",
}

_ANOMALY_ADVICE: dict[EventKind, str] = {
    EventKind.STILLNESS: "Segera periksa kondisinya.",
    EventKind.NOCTURNAL_MOVEMENT: "Ketuk untuk meninjau.",
    EventKind.BATHROOM_DURATION: "Mohon segera periksa.",
}


def _minutes(duration_s: float | None) -> str:
    if duration_s is None or duration_s <= 0:
        return ""
    return f" selama {max(1, round(duration_s / 60))} menit"


def anomaly_alert_text(*, camera_name: str, kind: EventKind,
                       duration_s: float | None = None) -> tuple[str, str]:
    label = _ANOMALY_LABELS.get(kind, "aktivitas tidak biasa")
    title = f"{_ANOMALY_TITLES.get(kind, 'Peringatan')} — {camera_name}"
    advice = _ANOMALY_ADVICE.get(kind, "Ketuk untuk meninjau.")
    body = f"Sistem mendeteksi {label}{_minutes(duration_s)} di {camera_name}. {advice}"
    return title, body


def escalation_text(*, camera_name: str, unresponsive_contact_name: str) -> tuple[str, str]:
    """Sent to the NEXT contact in the chain, naming who already missed it."""
    title = f"Belum direspons — {camera_name}"
    body = (
        f"{unresponsive_contact_name} belum menanggapi peringatan jatuh di "
        f"{camera_name}. Mohon segera periksa."
    )
    return title, body
