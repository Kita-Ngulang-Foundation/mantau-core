"""Device push tokens — registered on login, refreshed on use, pruned on death.

`TokenStore` is a Protocol: each backend implements it against its own
SQLite (`store/token_store.py` in both backend repos), so this package never
opens a database connection itself. `FCMPushChannel` calls `prune`/`touch` by
raw token string — that string is the entire identity FCM needs, so nothing
here has to know which member or household a device belongs to.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field


class Platform(str, Enum):
    ANDROID = "android"
    IOS = "ios"


class DeviceToken(BaseModel):
    device_id: str
    platform: Platform
    token: str
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TokenStore(Protocol):
    def register(self, token: DeviceToken) -> None:
        """Insert or replace — a device re-registering (app reinstall, token
        rotation) must not create a duplicate row."""
        ...

    def tokens_for_camera(self, camera_id: str) -> list[DeviceToken]:
        ...

    def touch(self, token: str, *, at: datetime | None = None) -> None:
        """Bump last_seen_at after a successful send — cheap evidence a token is still live."""
        ...

    def prune(self, token: str) -> None:
        """Delete permanently. Called only when FCM itself says UNREGISTERED —
        never speculatively, or a transient error would silently stop future alerts."""
        ...
