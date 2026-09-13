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
