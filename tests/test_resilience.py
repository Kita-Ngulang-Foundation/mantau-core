"""Backoff math must be exact at the jitter extremes, and the supervisor must
actually restart, actually stop, and actually give up when told to."""

import asyncio

import pytest

from mantau_core.resilience import (
    BackoffPolicy,
    RestartBudgetExhausted,
    Supervisor,
    compute_delay,
)


def test_compute_delay_zero_jitter_is_zero():
    assert compute_delay(5, base=1.0, cap=100.0, rand=lambda: 0.0) == 0.0


def test_compute_delay_max_jitter_hits_the_exponential_ceiling():
    assert compute_delay(3, base=0.5, cap=100.0, rand=lambda: 1.0) == 0.5 * 2 ** 3


def test_compute_delay_is_capped():
    assert compute_delay(20, base=1.0, cap=5.0, rand=lambda: 1.0) == 5.0


def test_backoff_policy_run_retries_then_succeeds():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("not yet")
        return "connected"

    policy = BackoffPolicy(base=0.001, cap=0.005)
    result = asyncio.run(policy.run(flaky))
    assert result == "connected"
    assert calls["n"] == 3


def test_backoff_policy_run_raises_after_max_attempts():
    async def always_fails():
        raise ConnectionError("nope")

    policy = BackoffPolicy(base=0.001, cap=0.005, max_attempts=2)
    with pytest.raises(ConnectionError):
        asyncio.run(policy.run(always_fails))


def test_supervisor_clean_return_ends_supervision_with_no_restarts():
    async def finishes_immediately():
        return

    sup = Supervisor("puller", finishes_immediately)
    asyncio.run(sup.run_forever())
    assert sup.status().restarts == 0
    assert sup.status().running is False


def test_supervisor_restarts_then_succeeds():
    calls = {"n": 0}

    async def fails_twice_then_ok():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ConnectionError("camera reset")
        return

    sup = Supervisor("puller", fails_twice_then_ok,
                      backoff=BackoffPolicy(base=0.001, cap=0.005))
    asyncio.run(sup.run_forever())
    assert calls["n"] == 3
    assert sup.status().restarts == 2


def test_supervisor_gives_up_after_restart_budget_exhausted():
    async def always_fails():
        raise ConnectionError("camera gone")

    sup = Supervisor("puller", always_fails,
                      backoff=BackoffPolicy(base=0.001, cap=0.002),
                      max_restarts=3, window_s=60.0)
    with pytest.raises(RestartBudgetExhausted):
        asyncio.run(sup.run_forever())
    assert sup.status().restarts > 3


def test_supervisor_does_not_start_once_stop_event_is_set():
    stop = asyncio.Event()
    stop.set()  # simulate a shutdown requested before the loop gets to run again

    async def never_called():
        raise AssertionError("task_factory must not run once stop_event is set")

    sup = Supervisor("uplink", never_called, backoff=BackoffPolicy(base=0.001, cap=0.002))
    asyncio.run(sup.run_forever(stop_event=stop))
    assert sup.status().running is False
    assert sup.status().restarts == 0
