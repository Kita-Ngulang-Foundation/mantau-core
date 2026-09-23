from mantau_core.contracts import EventKind, FallEvent
from mantau_core.notify.templates import id_id, render


def test_fall_alert_text_includes_camera_and_confidence():
    title, body = id_id.fall_alert_text(camera_name="Kamar Ibu", confidence=0.87)
    assert "Kamar Ibu" in title
    assert "87%" in body


def test_anomaly_alert_text_uses_the_kind_specific_label():
    title, body = id_id.anomaly_alert_text(camera_name="Kamar Ibu", kind=EventKind.STILLNESS)
    assert "diam berkepanjangan" in body


def test_render_dispatches_fall_events_to_fall_copy():
    event = FallEvent(camera_id="cam-1", kind=EventKind.FALL, confidence=0.9)
    title, body = render(event, camera_name="Kamar Ibu")
    assert "Jatuh terdeteksi" in title


def test_render_dispatches_anomaly_events_to_anomaly_copy():
    event = FallEvent(camera_id="cam-1", kind=EventKind.NOCTURNAL_MOVEMENT)
    title, body = render(event, camera_name="Kamar Ibu")
    assert "gerakan di malam hari" in body


def test_each_anomaly_kind_has_its_own_title_and_duration():
    cases = {
        EventKind.STILLNESS: "Tidak bergerak terlalu lama",
        EventKind.NOCTURNAL_MOVEMENT: "Aktivitas malam tidak biasa",
        EventKind.BATHROOM_DURATION: "Terlalu lama di kamar mandi",
    }
    for kind, title_text in cases.items():
        event = FallEvent(camera_id="cam-1", kind=kind, signals={"duration_s": 1500.0})
        title, body = render(event, camera_name="Kamar Ibu")
        assert title == f"{title_text} — Kamar Ibu"
        assert "25 menit" in body


def test_default_severity_per_kind():
    from mantau_core.contracts import Severity, default_severity

    assert default_severity(EventKind.FALL) is Severity.CRITICAL
    assert default_severity(EventKind.STILLNESS) is Severity.CRITICAL
    assert default_severity(EventKind.BATHROOM_DURATION) is Severity.WARNING
    assert default_severity(EventKind.NOCTURNAL_MOVEMENT) is Severity.WARNING
