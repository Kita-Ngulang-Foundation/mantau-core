from mantau_core.contracts import FallEvent
from mantau_core.notify.alert import Alert
from mantau_core.notify.channels.push.payload import ANDROID_CHANNEL_ID, build_fcm_message


def _alert() -> Alert:
    event = FallEvent(camera_id="cam-1", confidence=0.9)
    return Alert.from_event(event, camera_name="Kamar Ibu", title="Jatuh terdeteksi", body="...")


def test_message_targets_the_right_token_and_channel():
    msg = build_fcm_message(token="tok-abc", alert=_alert())["message"]
    assert msg["token"] == "tok-abc"
    assert msg["android"]["notification"]["channel_id"] == ANDROID_CHANNEL_ID


def test_android_priority_is_high_to_bypass_doze():
    msg = build_fcm_message(token="t", alert=_alert())["message"]
    assert msg["android"]["priority"] == "high"


def test_apns_priority_is_immediate():
    msg = build_fcm_message(token="t", alert=_alert())["message"]
    assert msg["apns"]["headers"]["apns-priority"] == "10"


def test_collapse_key_matches_across_android_tag_and_apns_id():
    alert = _alert()
    msg = build_fcm_message(token="t", alert=alert)["message"]
    assert msg["android"]["notification"]["tag"] == alert.collapse_key
    assert msg["apns"]["headers"]["apns-collapse-id"] == alert.collapse_key[:64]


def test_data_payload_carries_the_deep_link_for_tap_handling():
    alert = _alert()
    msg = build_fcm_message(token="t", alert=alert)["message"]
    assert msg["data"]["event_id"] == alert.event_id
    assert msg["data"]["deep_link"] == alert.deep_link


def test_apns_collapse_id_is_truncated_to_64_bytes():
    event = FallEvent(camera_id="cam-1")
    alert = Alert.from_event(event, camera_name="x", title="t", body="b")
    # collapse_key is "fall:<32 hex chars>" (36 chars) -- well under 64, but
    # prove the truncation guard actually holds regardless of key length.
    long_alert = alert.model_copy(update={"collapse_key": "x" * 100})
    msg = build_fcm_message(token="t", alert=long_alert)["message"]
    assert len(msg["apns"]["headers"]["apns-collapse-id"]) == 64


def test_payload_carries_the_event_kind_and_collapses_per_event():
    from mantau_core.contracts import EventKind

    event = FallEvent(camera_id="cam-1", kind=EventKind.BATHROOM_DURATION)
    alert = Alert.from_event(event, camera_name="Kamar mandi", title="t", body="b")
    msg = build_fcm_message(token="t", alert=alert)["message"]
    assert msg["data"]["kind"] == "bathroom_duration"
    assert msg["android"]["notification"]["tag"] == f"bathroom_duration:{event.event_id}"
    assert build_fcm_message(token="t", alert=_alert())["message"]["data"]["kind"] == "fall"
