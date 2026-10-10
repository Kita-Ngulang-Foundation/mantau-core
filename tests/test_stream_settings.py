import pytest
from pydantic import ValidationError

from mantau_core.contracts import DetectionSettings, StreamSettings


def test_defaults_are_what_agents_sent_before_the_section_existed():
    stream = DetectionSettings().stream
    assert stream == StreamSettings(max_width=640, jpeg_quality=65, detection_fps=10.0,
                                    live_from_detection=False, motion_saver=False)


def test_settings_saved_before_the_section_existed_still_parse():
    settings = DetectionSettings.model_validate({"version": 3, "stillness": {"floor_minutes": 2}})
    assert settings.stream == StreamSettings()
    assert settings.stillness.floor_minutes == 2


def test_round_trip_keeps_every_field():
    changed = DetectionSettings().model_dump(mode="json")
    changed["stream"] = {"max_width": 384, "jpeg_quality": 50, "detection_fps": 5,
                         "live_from_detection": True, "motion_saver": True}
    parsed = DetectionSettings.model_validate(changed)
    assert parsed.stream.max_width == 384
    assert parsed.stream.jpeg_quality == 50
    assert parsed.stream.detection_fps == 5
    assert parsed.stream.live_from_detection and parsed.stream.motion_saver
    assert DetectionSettings.model_validate(parsed.model_dump(mode="json")) == parsed


@pytest.mark.parametrize("field,value", [
    ("max_width", 500), ("max_width", 1280), ("jpeg_quality", 20), ("jpeg_quality", 95),
    ("detection_fps", 1.0), ("detection_fps", 15.0), ("unknown", 1),
])
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        StreamSettings.model_validate({field: value})


def test_stream_change_preserves_an_episode_in_progress():
    from mantau_core.activity import ActivityEngine, default_rules
    from test_activity_rules import _load, _replay
    fixture = _load("floor_lying_pages_critical")
    baseline = _replay(fixture)
    engine = ActivityEngine(default_rules(), DetectionSettings.model_validate(fixture["settings"]))
    split = len(fixture["steps"]) // 2
    events = _replay(fixture, fixture["steps"][:split], engine)
    changed = engine.settings.model_dump(mode="json")
    changed["version"] += 1
    changed["stream"] = {"max_width": 320, "jpeg_quality": 35, "detection_fps": 2,
                         "live_from_detection": True, "motion_saver": True}
    engine.apply_settings(DetectionSettings.model_validate(changed))
    events += _replay(fixture, fixture["steps"][split:], engine)
    assert [(e.kind, e.occurred_at, e.signals) for e in events] == [
        (e.kind, e.occurred_at, e.signals) for e in baseline]


def test_a_rule_change_still_resets_episodes():
    from mantau_core.activity import ActivityEngine, default_rules
    engine = ActivityEngine(default_rules(), DetectionSettings())
    resets = []
    for rule in engine.rules:
        original = rule.reset
        rule.reset = (lambda original=original: (resets.append(1), original()))
    changed = DetectionSettings().model_dump(mode="json")
    changed["version"] = 2
    changed["stream"] = {"max_width": 320}
    changed["stillness"] = {"floor_minutes": 5}
    engine.apply_settings(DetectionSettings.model_validate(changed))
    assert len(resets) == len(engine.rules)
