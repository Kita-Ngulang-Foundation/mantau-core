"""Settings every backend needs, whatever scenario it implements.

Each backend extends this with its own fields (`mantau_rtsp.config.Settings`,
`mantau_ld.server.config.Settings`) rather than redeclaring these — env var
names below (`MANTAU_...`) are the ones ops/docker-compose actually set, so
keep a subclass's own fields on a different prefix if you add a nested
settings group, to avoid an accidental collision.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MANTAU_", env_file=".env", extra="ignore")

    environment: str = "dev"  # dev | staging | prod — never branch logic on this beyond config
    log_level: str = "INFO"

    # -- push (channels/push/fcm.py) --------------------------------------
    fcm_project_id: str | None = None
    fcm_service_account_path: str | None = None

    # -- telegram (channels/telegram.py) -- TEMPORARY, see that module -----
    telegram_bot_token: str | None = None

    # -- resilience defaults, overridable per call site ---------------------
    backoff_base_s: float = 0.5
    backoff_cap_s: float = 30.0

    # -- buffer/spool.py -----------------------------------------------------
    spool_ttl_s: float = Field(default=300.0, description="How long an unacked "
                               "event is kept locally through an outage (~5 min).")

    @property
    def push_configured(self) -> bool:
        return bool(self.fcm_project_id and self.fcm_service_account_path)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)
