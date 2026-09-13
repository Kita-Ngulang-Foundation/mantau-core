import pytest

from mantau_core.telemetry import Counter, Gauge, LatencyTrace, MetricsRegistry, Stage


def _fake_clock(times):
    it = iter(times)
    return lambda: next(it)


def test_latency_trace_elapsed_between_two_stages():
    trace = LatencyTrace("ev-1", clock=_fake_clock([100.0, 101.2, 101.5, 102.9]))
    trace.stamp(Stage.CAPTURED)
    trace.stamp(Stage.DETECTED)
    trace.stamp(Stage.QUEUED)
    trace.stamp(Stage.SENT)
    assert trace.elapsed(start=Stage.CAPTURED, end=Stage.SENT) == pytest.approx(2.9)


def test_latency_trace_elapsed_is_none_before_both_stages_seen():
    trace = LatencyTrace("ev-1", clock=_fake_clock([100.0]))
    trace.stamp(Stage.CAPTURED)
    assert trace.elapsed(start=Stage.CAPTURED, end=Stage.DELIVERED) is None


def test_within_budget_true_and_false():
    fast = LatencyTrace("ev-fast", clock=_fake_clock([0.0, 3.0]))
    fast.stamp(Stage.CAPTURED)
    fast.stamp(Stage.DELIVERED)
    assert fast.within_budget(5.0) is True

    slow = LatencyTrace("ev-slow", clock=_fake_clock([0.0, 7.0]))
    slow.stamp(Stage.CAPTURED)
    slow.stamp(Stage.DELIVERED)
    assert slow.within_budget(5.0) is False


def test_within_budget_none_while_in_flight():
    trace = LatencyTrace("ev-1", clock=_fake_clock([0.0]))
    trace.stamp(Stage.CAPTURED)
    assert trace.within_budget(5.0) is None


def test_ack_keeps_the_first_of_several():
    trace = LatencyTrace("ev-1", clock=_fake_clock([0.0]))
    trace.stamp(Stage.CAPTURED, at=0.0)
    trace.stamp(Stage.ACKED, at=6.0)   # son's phone, slower
    trace.stamp(Stage.ACKED, at=4.5)   # daughter's phone, first to see it
    assert trace.elapsed(end=Stage.ACKED) == 4.5
    assert trace.ack_count() == 2


def test_to_summary_reports_seconds_since_captured():
    trace = LatencyTrace("ev-1")
    trace.stamp(Stage.CAPTURED, at=1000.0)
    trace.stamp(Stage.DETECTED, at=1000.4)
    trace.stamp(Stage.DELIVERED, at=1003.1)
    summary = trace.to_summary()
    assert summary["captured"] == 0.0
    assert round(summary["detected"], 2) == 0.4
    assert round(summary["delivered"], 2) == 3.1
    assert summary["acked"] is None


def test_counter_and_gauge_are_thread_safe_enough_for_simple_use():
    c = Counter()
    c.inc()
    c.inc(2.5)
    assert c.value == 3.5

    g = Gauge()
    g.set(10)
    g.inc(5)
    g.dec(3)
    assert g.value == 12


def test_metrics_registry_snapshot():
    reg = MetricsRegistry()
    reg.counter("events.fall").inc()
    reg.counter("events.fall").inc()
    reg.gauge("spool.depth").set(4)
    snap = reg.snapshot()
    assert snap["counter.events.fall"] == 2.0
    assert snap["gauge.spool.depth"] == 4.0
