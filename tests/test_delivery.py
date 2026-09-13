from mantau_core.notify.delivery import AckService, DeliveryTracker
from mantau_core.notify.protocol import Delivery, DeliveryStatus


def test_tracker_records_history_per_event_and_target():
    tracker = DeliveryTracker()
    tracker.record(Delivery(event_id="ev-1", status=DeliveryStatus.SENT), target="tok-a")
    tracker.record(Delivery(event_id="ev-1", status=DeliveryStatus.DELIVERED), target="tok-a")
    tracker.record(Delivery(event_id="ev-1", status=DeliveryStatus.FAILED), target="tok-b")

    assert tracker.latest("ev-1", "tok-a").status is DeliveryStatus.DELIVERED
    assert len(tracker.all_for_event("ev-1")) == 3
    assert tracker.any_delivered("ev-1") is True


def test_tracker_any_delivered_false_when_all_failed():
    tracker = DeliveryTracker()
    tracker.record(Delivery(event_id="ev-1", status=DeliveryStatus.FAILED), target="tok-a")
    assert tracker.any_delivered("ev-1") is False


def test_ack_reports_first_ack_and_ignores_repeats():
    svc = AckService()
    assert svc.ack("ev-1", member_id="anak") is True
    assert svc.ack("ev-1", member_id="anak") is False   # same person acking twice
    assert svc.ack("ev-1", member_id="cucu") is False   # a second person, but not first
    assert svc.acked_by("ev-1") == {"anak", "cucu"}


def test_on_first_ack_callback_fires_exactly_once():
    calls = []
    svc = AckService()
    svc.on_first_ack("ev-1", lambda member_id: calls.append(member_id))

    svc.ack("ev-1", member_id="anak")
    svc.ack("ev-1", member_id="cucu")

    assert calls == ["anak"]


def test_is_acked_reflects_state():
    svc = AckService()
    assert svc.is_acked("ev-1") is False
    svc.ack("ev-1", member_id="anak")
    assert svc.is_acked("ev-1") is True
