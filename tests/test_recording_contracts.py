import pytest
from pydantic import ValidationError
from mantau_core.contracts import AgentRecordingsSnapshot, DetectionSettings, CommandType


def test_recording_toggle_preserves_in_progress_activity_episode():
    from mantau_core.activity import ActivityEngine, default_rules
    from test_activity_rules import _load, _replay
    fixture = _load("floor_lying_pages_critical")
    baseline = _replay(fixture)
    engine = ActivityEngine(default_rules(), DetectionSettings.model_validate(fixture["settings"]))
    split = len(fixture["steps"]) // 2
    events = _replay(fixture, fixture["steps"][:split], engine)
    changed = engine.settings.model_dump(mode="json")
    changed["version"] += 1
    changed["recordings"] = {"enabled": False}
    engine.apply_settings(DetectionSettings.model_validate(changed))
    events += _replay(fixture, fixture["steps"][split:], engine)
    assert [(e.kind, e.occurred_at, e.signals) for e in events] == [
        (e.kind, e.occurred_at, e.signals) for e in baseline]


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
