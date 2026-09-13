"""TEMPORARY. Demo insurance for this weekend, not the product.

Push (channels/push/) is the real channel and gets built to completion;
Telegram exists so a live demo still produces an alert if FCM misbehaves on
the day, and as a control — if latency hits budget on Telegram but not on
push, the delay is in delivery, not in detection. Delete this file once push
is proven end-to-end in the field; do not build anything new on top of it.

`target` is a chat_id (str) — a family member's own chat with the bot, or a
group chat standing in for the household. No token lifecycle to manage,
which is most of why this was fast to stand up for the weekend.
"""

from __future__ import annotations

import httpx

from mantau_core.notify.alert import Alert
from mantau_core.notify.protocol import Delivery, DeliveryStatus


class TelegramChannel:
    def __init__(self, bot_token: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._bot_token = bot_token
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def send(self, alert: Alert, target: str) -> Delivery:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        text = f"{alert.title}\n\n{alert.body}"
        resp = await self._client.post(url, json={"chat_id": target, "text": text})
        ok = False
        try:
            ok = resp.status_code == 200 and bool(resp.json().get("ok"))
        except ValueError:
            pass
        if ok:
            return Delivery(event_id=alert.event_id, status=DeliveryStatus.DELIVERED, detail=target)
        return Delivery(event_id=alert.event_id, status=DeliveryStatus.FAILED, detail=resp.text)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
