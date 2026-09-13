"""The channel-agnostic shapes: what sending returns, and the interface every
channel (push, Telegram, console) implements identically.

`Notifier.send` takes a plain `target: str` — an FCM token, a Telegram chat
id — rather than a richer recipient object, so this protocol never needs to
know about devices, tokens, or chat ids. Resolving "who" is `recipients.py`'s
job; a channel only needs to know "where."
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from .alert import Alert


class DeliveryStatus(str, Enum):
    SENT = "sent"            # handed to the channel's transport (HTTP call made)
    ACCEPTED = "accepted"    # the channel's server accepted it (e.g. FCM 200)
    DELIVERED = "delivered"  # best signal a channel gives short of a device ack
    FAILED = "failed"


class Delivery(BaseModel):
    event_id: str
    status: DeliveryStatus
    detail: str = ""
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Notifier(Protocol):
    async def send(self, alert: Alert, target: str) -> Delivery:
        ...

    async def close(self) -> None:
        ...
