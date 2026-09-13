from mantau_core.config import CoreSettings


def test_defaults_are_safe_for_a_fresh_checkout():
    settings = CoreSettings(_env_file=None)
    assert settings.push_configured is False
    assert settings.telegram_configured is False
    assert settings.spool_ttl_s == 300.0


def test_push_configured_requires_both_project_id_and_service_account():
    only_project = CoreSettings(_env_file=None, fcm_project_id="mantau-prod")
    assert only_project.push_configured is False

    both = CoreSettings(_env_file=None, fcm_project_id="mantau-prod",
                         fcm_service_account_path="/secrets/fcm.json")
    assert both.push_configured is True


def test_env_vars_use_the_mantau_prefix(monkeypatch):
    monkeypatch.setenv("MANTAU_TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("MANTAU_ENVIRONMENT", "prod")
    settings = CoreSettings(_env_file=None)
    assert settings.telegram_configured is True
    assert settings.environment == "prod"


def test_a_backend_can_subclass_with_its_own_fields():
    class RtspSettings(CoreSettings):
        max_cameras: int = 4

    settings = RtspSettings(_env_file=None)
    assert settings.max_cameras == 4
    assert settings.spool_ttl_s == 300.0  # inherited default still applies
