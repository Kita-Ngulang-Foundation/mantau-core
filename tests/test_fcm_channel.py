"""FCMPushChannel against a mocked HTTP transport -- no real network, no real
Google Cloud project. Exercises the two paths that matter: a clean send
touches the token, and an UNREGISTERED response prunes it and never retries
blindly.
"""

import asyncio

import httpx
import pytest

from mantau_core.contracts import FallEvent
from mantau_core.notify.alert import Alert
from mantau_core.notify.channels.push.errors import PushDeliveryError, PushErrorKind
from mantau_core.notify.channels.push.fcm import FCMPushChannel
from mantau_core.notify.protocol import DeliveryStatus


class _FakeCredentials:
    def access_token(self) -> str:
        return "fake-bearer-token"


class _FakeTokenStore:
    def __init__(self) -> None:
        self.touched: list[str] = []
        self.pruned: list[str] = []

    def register(self, token) -> None:
        raise NotImplementedError

    def tokens_for_camera(self, camera_id: str) -> list:
        raise NotImplementedError

    def touch(self, token: str, *, at=None) -> None:
        self.touched.append(token)

    def prune(self, token: str) -> None:
        self.pruned.append(token)


def _alert() -> Alert:
    event = FallEvent(camera_id="cam-1", confidence=0.92)
    return Alert.from_event(event, camera_name="Kamar Ibu", title="Jatuh terdeteksi", body="body")


def test_successful_send_touches_the_token_and_returns_delivered():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fake-bearer-token"
        return httpx.Response(200, json={"name": "projects/p/messages/123"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = _FakeTokenStore()
    channel = FCMPushChannel("proj", _FakeCredentials(), tokens, client=client)

    delivery = asyncio.run(channel.send(_alert(), "tok-abc"))

    assert delivery.status is DeliveryStatus.DELIVERED
    assert tokens.touched == ["tok-abc"]
    assert tokens.pruned == []
    asyncio.run(client.aclose())


def test_unregistered_response_prunes_and_raises_without_touching():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={
            "error": {"status": "NOT_FOUND", "message": "Requested entity was not found.",
                      "details": [{"errorCode": "UNREGISTERED"}]}
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = _FakeTokenStore()
    channel = FCMPushChannel("proj", _FakeCredentials(), tokens, client=client)

    with pytest.raises(PushDeliveryError) as exc_info:
        asyncio.run(channel.send(_alert(), "dead-token"))

    assert exc_info.value.kind is PushErrorKind.UNREGISTERED
    assert tokens.pruned == ["dead-token"]
    assert tokens.touched == []
    asyncio.run(client.aclose())


def test_server_error_raises_retryable_without_pruning():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"status": "INTERNAL", "message": "boom"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tokens = _FakeTokenStore()
    channel = FCMPushChannel("proj", _FakeCredentials(), tokens, client=client)

    with pytest.raises(PushDeliveryError) as exc_info:
        asyncio.run(channel.send(_alert(), "tok-abc"))

    assert exc_info.value.kind is PushErrorKind.RETRYABLE
    assert tokens.pruned == []
    asyncio.run(client.aclose())
