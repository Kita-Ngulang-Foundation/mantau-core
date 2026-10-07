import pytest
from pydantic import ValidationError
from mantau_core.contracts import AgentRecordingsSnapshot, DetectionSettings, CommandType


def test_existing_saved_settings_keep_detection_values_when_recording_is_disabled():
    settings = DetectionSettings.model_validate({"stillness": {"floor_minutes": 7}})
    assert settings.recordings.enabled is True
    changed = settings.model_dump(mode="json")
    changed["recordings"] = {"enabled": False}
    parsed = DetectionSettings.model_validate(changed)
    assert parsed.recordings.enabled is False
    assert parsed.stillness.floor_minutes == 7
    assert parsed.fall == settings.fall
    assert parsed.zones == settings.zones
    assert CommandType.UPLOAD_RECORDING.value == "upload_recording"


def test_snapshot_has_a_fixed_five_clip_limit_and_rejects_paths_and_unbounded_payloads():
    row = {"event_id": "event-1", "size_bytes": 200, "captured_at_ms": 10}
    assert len(AgentRecordingsSnapshot(recordings=[row]).recordings) == 1
    for values in ([row] * 6, [{**row, "event_id": "../other"}],
                   [{**row, "size_bytes": 21 * 1024 * 1024}], [{**row, "path": "/private/file"}]):
        with pytest.raises(ValidationError):
            AgentRecordingsSnapshot(recordings=values)
