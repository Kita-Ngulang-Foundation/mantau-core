import pytest
from pydantic import ValidationError
from mantau_core.contracts import DetectionSettings


def test_old_camera_settings_receive_research_defaults_and_keep_floor_backup():
    settings = DetectionSettings.model_validate({"version": 7})
    assert settings.fall.model == "research"
    assert (settings.fall.tau_loose, settings.fall.tau_high) == (0.92, 0.98)
    assert (settings.fall.confirm_loose_s, settings.fall.confirm_high_s) == (15, 5)
    assert settings.fall.down_share == 0.6
    assert (settings.fall.min_track_age_s, settings.fall.max_edge_frac) == (0, 1)
    assert settings.stillness.floor_minutes == 0.5


@pytest.mark.parametrize("fall", [
    {"tau_loose": 0.99, "tau_high": 0.95}, {"confirm_high_s": 20},
    {"down_share": 0}, {"confirm_loose_s": 0}, {"model": "unknown"},
    {"tau_high": float("nan")}, {"max_edge_frac": 2},
])
def test_bad_confirmation_settings_are_rejected(fall):
    with pytest.raises(ValidationError):
        DetectionSettings.model_validate({"fall": fall})


def test_per_camera_s1b_rollback_preserves_activity_settings():
    settings = DetectionSettings.model_validate({"fall": {"model": "s1b"}, "bathroom": {"warning_minutes": 25}})
    assert settings.fall.model == "s1b"
    assert settings.bathroom.warning_minutes == 25
    assert DetectionSettings.model_validate_json(settings.model_dump_json()) == settings
