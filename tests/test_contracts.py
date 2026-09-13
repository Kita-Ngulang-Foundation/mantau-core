"""Contracts must survive a JSON round-trip and the envelope must actually verify."""

from mantau_core.contracts import (
    CameraRef,
    Credentials,
    Envelope,
    FallEvent,
    Heartbeat,
    StreamProfile,
)


def test_fall_event_json_roundtrip():
    ev = FallEvent(camera_id="cam-1", confidence=0.91, track_id=3,
                    signals={"velocity": 0.52, "torso_angle_deg": 84.0})
    raw = ev.model_dump_json()
    back = FallEvent.model_validate_json(raw)
    assert back.camera_id == "cam-1"
    assert back.confidence == 0.91
    assert back.signals["torso_angle_deg"] == 84.0
    assert back.event_id == ev.event_id  # id is stable across the round-trip


def test_fall_event_default_ids_are_unique():
    a, b = FallEvent(camera_id="cam-1"), FallEvent(camera_id="cam-1")
    assert a.event_id != b.event_id


def test_camera_stream_url_prefers_sub_and_hides_password_in_repr():
    cam = CameraRef(
        camera_id="cam-1", name="Kamar Ibu", host="192.168.1.42",
        paths={StreamProfile.MAIN: "/stream1", StreamProfile.SUB: "/stream2"},
        credentials=Credentials(username="admin", password="s3cret"),
    )
    url = cam.stream_url(StreamProfile.SUB)
    assert url == "rtsp://admin:s3cret@192.168.1.42:554/stream2"
    assert "s3cret" not in repr(cam.credentials)


def test_camera_stream_url_falls_back_to_main_without_sub():
    cam = CameraRef(camera_id="cam-1", name="Kamar Ibu", host="192.168.1.42",
                     paths={StreamProfile.MAIN: "/stream1"})
    assert cam.stream_url(StreamProfile.SUB) == "rtsp://192.168.1.42:554/stream1"


def test_envelope_sign_and_verify_round_trip():
    event = FallEvent(camera_id="cam-1", confidence=0.8)
    env = Envelope.for_event("agent-1", seq=7, event=event).sign("shared-secret")
    assert env.verify("shared-secret") is True
    assert env.verify("wrong-secret") is False
    assert env.event().event_id == event.event_id


def test_envelope_unsigned_never_verifies():
    env = Envelope.for_heartbeat(
        "agent-1", seq=1,
        heartbeat=Heartbeat(agent_id="agent-1", camera_reachable=True, detector_alive=True),
    )
    assert env.verify("any-secret") is False


def test_envelope_tamper_detection():
    event = FallEvent(camera_id="cam-1", confidence=0.8)
    env = Envelope.for_event("agent-1", seq=1, event=event).sign("shared-secret")
    tampered = env.model_copy(update={"seq": 999})
    assert tampered.verify("shared-secret") is False
