import asyncio

import httpx

from mantau_core.contracts import FallEvent
from mantau_core.notify.alert import Alert
from mantau_core.notify.channels.telegram import TelegramChannel
from mantau_core.notify.protocol import DeliveryStatus


def _alert() -> Alert:
    event = FallEvent(camera_id="cam-1", confidence=0.8)
    return Alert.from_event(event, camera_name="Kamar Ibu", title="Jatuh terdeteksi", body="body")


def test_successful_send_reports_delivered():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "bot123" in str(request.url)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = TelegramChannel("123", client=client)

    delivery = asyncio.run(channel.send(_alert(), "chat-42"))

    assert delivery.status is DeliveryStatus.DELIVERED
    assert delivery.detail == "chat-42"
    asyncio.run(client.aclose())


def test_telegram_error_reports_failed_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "chat not found"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = TelegramChannel("123", client=client)

    delivery = asyncio.run(channel.send(_alert(), "bad-chat"))

    assert delivery.status is DeliveryStatus.FAILED
    asyncio.run(client.aclose())
