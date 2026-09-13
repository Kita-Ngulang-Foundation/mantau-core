"""FCM HTTP v1 — the channel that ships. OAuth2 service-account bearer token,
never the deprecated legacy server-key API (Google shut that migration
window; HTTP v1 is the only supported path for a new integration).

`google-auth` is imported lazily inside `ServiceAccountCredentials`, not at
module load — importing `mantau_core.notify` should never require a Google
Cloud dependency; only actually sending push does. Install it with:

    pip install "mantau-core[push]"
"""

from __future__ import annotations

from typing import Protocol

import httpx

from mantau_core.notify.alert import Alert
from mantau_core.notify.protocol import Delivery, DeliveryStatus

from .errors import PushDeliveryError, PushErrorKind, classify_fcm_error
from .payload import build_fcm_message
from .tokens import TokenStore


class CredentialsProvider(Protocol):
    """Supplies a fresh OAuth2 bearer token for FCM's HTTP v1 API."""

    def access_token(self) -> str: ...


class ServiceAccountCredentials:
    """Real `CredentialsProvider`, backed by a Firebase service-account JSON key."""

    _SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

    def __init__(self, service_account_path: str) -> None:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except ImportError as exc:
            raise ImportError(
                'FCM push requires google-auth. Install with `pip install "mantau-core[push]"`.'
            ) from exc
        self._request = Request()
        self._creds = service_account.Credentials.from_service_account_file(
            service_account_path, scopes=self._SCOPES
        )

    def access_token(self) -> str:
        if not self._creds.valid:
            self._creds.refresh(self._request)
        return self._creds.token


class FCMPushChannel:
    """`Notifier` for Android/iOS via Firebase Cloud Messaging.

    `target` is the raw FCM registration token. On success the token's
    `last_seen_at` is bumped; on an UNREGISTERED response it is pruned
    immediately — see `channels/push/errors.py` for why those two paths must
    never be conflated.
    """

    def __init__(
        self,
        project_id: str,
        credentials: CredentialsProvider,
        token_store: TokenStore,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.project_id = project_id
        self._credentials = credentials
        self._tokens = token_store
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def send(self, alert: Alert, target: str) -> Delivery:
        message = build_fcm_message(token=target, alert=alert)
        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        headers = {"Authorization": f"Bearer {self._credentials.access_token()}"}

        resp = await self._client.post(url, json=message, headers=headers)

        if resp.status_code == 200:
            self._tokens.touch(target)
            name = ""
            try:
                name = resp.json().get("name", "")
            except ValueError:
                pass
            return Delivery(event_id=alert.event_id, status=DeliveryStatus.DELIVERED, detail=name)

        body: dict = {}
        try:
            body = resp.json()
        except ValueError:
            pass
        kind = classify_fcm_error(resp.status_code, body)
        if kind is PushErrorKind.UNREGISTERED:
            self._tokens.prune(target)
        detail = body.get("error", {}).get("message", resp.text)
        raise PushDeliveryError(kind, detail)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
