"""One event -> every configured channel -> every target that channel resolves.

This is where "push is the product, Telegram is scaffolding" actually plays
out: configure one binding or several, and every event goes through whatever
is configured. A `ChannelBinding` pairs a `Notifier` with the (channel-
specific) logic for turning a camera into a list of targets, so `Fanout`
itself never needs to know what a target string means to any given channel.

When a `LatencyTrace` is passed in, `send()` stamps QUEUED/SENT/DELIVERED on
it — the same three stages `mantau-testbed/scenarios/compare.py` reads from
both backends to build one comparison table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mantau_core.contracts import FallEvent
from mantau_core.telemetry import LatencyTrace, Stage

from .alert import Alert
from .delivery.tracker import DeliveryTracker
from .protocol import Delivery, DeliveryStatus, Notifier
from .recipients import RecipientResolver
from .templates import render


class ChannelBinding(Protocol):
    notifier: Notifier

    def targets_for_camera(self, camera_id: str) -> list[str]:
        ...


@dataclass
class PushBinding:
    """Every registered device's push token, for this camera's account."""

    notifier: Notifier  # an FCMPushChannel
    resolver: RecipientResolver

    def targets_for_camera(self, camera_id: str) -> list[str]:
        return [d.token for d in self.resolver.devices_for_camera(camera_id)]


@dataclass
class TelegramBinding:
    """A fixed set of chat ids — TEMPORARY, matches the channel it wraps."""

    notifier: Notifier  # a TelegramChannel
    chat_ids: list[str]

    def targets_for_camera(self, camera_id: str) -> list[str]:
        return list(self.chat_ids)


@dataclass
class Fanout:
    channels: list[ChannelBinding]
    tracker: DeliveryTracker

    async def send(
        self, event: FallEvent, *, camera_name: str, trace: LatencyTrace | None = None
    ) -> list[Delivery]:
        if trace is not None:
            trace.stamp(Stage.QUEUED)

        title, body = render(event, camera_name=camera_name)
        alert = Alert.from_event(event, camera_name=camera_name, title=title, body=body)

        deliveries: list[Delivery] = []
        for binding in self.channels:
            for target in binding.targets_for_camera(event.camera_id):
                if trace is not None:
                    trace.stamp(Stage.SENT)
                try:
                    delivery = await binding.notifier.send(alert, target)
                except Exception as exc:  # noqa: BLE001 -- one bad target must not stop the rest
                    delivery = Delivery(event_id=event.event_id, status=DeliveryStatus.FAILED,
                                         detail=str(exc))
                else:
                    if trace is not None and delivery.status is DeliveryStatus.DELIVERED:
                        trace.stamp(Stage.DELIVERED)
                self.tracker.record(delivery, target=target)
                deliveries.append(delivery)
        return deliveries
