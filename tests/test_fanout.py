import asyncio

from mantau_core.contracts import FallEvent
from mantau_core.notify.channels.push.tokens import DeviceToken, Platform
from mantau_core.notify.delivery import DeliveryTracker
from mantau_core.notify.fanout import Fanout, FixedBinding, PushBinding, TelegramBinding
from mantau_core.notify.protocol import Delivery, DeliveryStatus
from mantau_core.telemetry import LatencyTrace, Stage


class _FakeResolver:
    def __init__(self, tokens: list[DeviceToken]) -> None:
        self._tokens = tokens

    def devices_for_camera(self, camera_id: str) -> list[DeviceToken]:
        return self._tokens

    def emergency_contacts_for_camera(self, camera_id: str) -> list:
        return []


class _FakeNotifier:
    def __init__(self, *, fail_targets: set[str] | None = None) -> None:
        self.sent: list[tuple[str, str]] = []  # (alert.title, target)
        self._fail_targets = fail_targets or set()

    async def send(self, alert, target: str) -> Delivery:
        self.sent.append((alert.title, target))
        if target in self._fail_targets:
            raise RuntimeError(f"channel rejected {target}")
        return Delivery(event_id=alert.event_id, status=DeliveryStatus.DELIVERED, detail=target)

    async def close(self) -> None:
        pass


def _fall_event() -> FallEvent:
    return FallEvent(camera_id="cam-1", confidence=0.9)


def test_fanout_sends_to_every_device_and_records_deliveries():
    devices = [
        DeviceToken(device_id="d1", platform=Platform.ANDROID, token="tok-1"),
        DeviceToken(device_id="d2", platform=Platform.ANDROID, token="tok-2"),
    ]
    notifier = _FakeNotifier()
    fanout = Fanout(
        channels=[PushBinding(notifier=notifier, resolver=_FakeResolver(devices))],
        tracker=DeliveryTracker(),
    )

    event = _fall_event()
    deliveries = asyncio.run(fanout.send(event, camera_name="Kamar Ibu"))

    assert {t for _, t in notifier.sent} == {"tok-1", "tok-2"}
    assert all(d.status is DeliveryStatus.DELIVERED for d in deliveries)
    assert fanout.tracker.any_delivered(event.event_id) is True


def test_fanout_one_bad_target_does_not_stop_the_rest():
    devices = [
        DeviceToken(device_id="d1", platform=Platform.ANDROID, token="dead"),
        DeviceToken(device_id="d2", platform=Platform.ANDROID, token="alive"),
    ]
    notifier = _FakeNotifier(fail_targets={"dead"})
    fanout = Fanout(
        channels=[PushBinding(notifier=notifier, resolver=_FakeResolver(devices))],
        tracker=DeliveryTracker(),
    )

    event = _fall_event()
    deliveries = asyncio.run(fanout.send(event, camera_name="Kamar Ibu"))
    statuses = {d.detail if d.status is DeliveryStatus.FAILED else None: d.status for d in deliveries}

    assert DeliveryStatus.DELIVERED in [d.status for d in deliveries]
    assert DeliveryStatus.FAILED in [d.status for d in deliveries]
    assert len(deliveries) == 2  # both targets attempted despite the failure


def test_fanout_sends_through_multiple_channels_at_once():
    devices = [DeviceToken(device_id="d1", platform=Platform.ANDROID, token="tok-1")]
    push_notifier = _FakeNotifier()
    telegram_notifier = _FakeNotifier()
    fanout = Fanout(
        channels=[
            PushBinding(notifier=push_notifier, resolver=_FakeResolver(devices)),
            TelegramBinding(notifier=telegram_notifier, chat_ids=["chat-42"]),
        ],
        tracker=DeliveryTracker(),
    )

    asyncio.run(fanout.send(_fall_event(), camera_name="Kamar Ibu"))

    assert push_notifier.sent == [("Jatuh terdeteksi — Kamar Ibu", "tok-1")]
    assert telegram_notifier.sent == [("Jatuh terdeteksi — Kamar Ibu", "chat-42")]


def test_fanout_stamps_the_latency_trace():
    devices = [DeviceToken(device_id="d1", platform=Platform.ANDROID, token="tok-1")]
    notifier = _FakeNotifier()
    fanout = Fanout(
        channels=[PushBinding(notifier=notifier, resolver=_FakeResolver(devices))],
        tracker=DeliveryTracker(),
    )

    event = _fall_event()
    trace = LatencyTrace(event.event_id)
    trace.stamp(Stage.CAPTURED)
    trace.stamp(Stage.DETECTED)

    asyncio.run(fanout.send(event, camera_name="Kamar Ibu", trace=trace))

    assert trace.has(Stage.QUEUED)
    assert trace.has(Stage.SENT)
    assert trace.has(Stage.DELIVERED)
    assert trace.within_budget(5.0) is True


def test_fixed_binding_always_fires_regardless_of_camera():
    notifier = _FakeNotifier()
    fanout = Fanout(channels=[FixedBinding(notifier=notifier, targets=["console"])],
                    tracker=DeliveryTracker())

    asyncio.run(fanout.send(_fall_event(), camera_name="Kamar Ibu"))

    assert notifier.sent == [("Jatuh terdeteksi — Kamar Ibu", "console")]


def test_regression_a_devicefree_pushbinding_never_fires_but_fixedbinding_does():
    """The exact bug FixedBinding exists to fix: a console/dev fallback
    wrapped in PushBinding with no registered devices silently never sends
    -- PushBinding resolves targets from the resolver, and an empty
    resolver means an empty target list, means the loop body never runs."""
    empty_resolver = _FakeResolver(tokens=[])
    broken_notifier = _FakeNotifier()
    broken_fanout = Fanout(
        channels=[PushBinding(notifier=broken_notifier, resolver=empty_resolver)],
        tracker=DeliveryTracker(),
    )
    asyncio.run(broken_fanout.send(_fall_event(), camera_name="Kamar Ibu"))
    assert broken_notifier.sent == []  # confirms the bug this fix addresses

    fixed_notifier = _FakeNotifier()
    fixed_fanout = Fanout(
        channels=[FixedBinding(notifier=fixed_notifier, targets=["console"])],
        tracker=DeliveryTracker(),
    )
    asyncio.run(fixed_fanout.send(_fall_event(), camera_name="Kamar Ibu"))
    assert fixed_notifier.sent == [("Jatuh terdeteksi — Kamar Ibu", "console")]
