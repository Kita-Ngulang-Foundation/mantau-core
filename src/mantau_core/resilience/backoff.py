"""Exponential backoff with full jitter (the AWS "full jitter" formula).

Full jitter — `delay = random(0, min(cap, base * 2**attempt))` — beats a flat
retry interval or jitter-free exponential backoff because when many things
fail together (a camera drops, a tunnel drops), full jitter spreads the
retries out instead of having them all collide again on the next tick.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


def compute_delay(
    attempt: int,
    *,
    base: float = 0.5,
    cap: float = 30.0,
    rand: Callable[[], float] = random.random,
) -> float:
    """Delay (seconds) before retry number `attempt` (0-indexed).

    `rand` is injectable so tests can pin it to 0.0 / 1.0 and assert exact
    bounds instead of asserting a range and hoping.
    """
    ceiling = min(cap, base * (2 ** attempt))
    return ceiling * rand()


@dataclass(frozen=True)
class BackoffPolicy:
    """A reusable retry shape. Reconnecting RTSP and reconnecting a tunnel
    can use different bases/caps but the same policy object shape."""

    base: float = 0.5
    cap: float = 30.0
    max_attempts: int | None = None  # None = retry forever

    def delay_for(self, attempt: int) -> float:
        return compute_delay(attempt, base=self.base, cap=self.cap)

    async def run(
        self,
        fn: Callable[[], Awaitable[T]],
        *,
        retry_on: tuple[type[BaseException], ...] = (Exception,),
        on_retry: Callable[[int, BaseException, float], None] | None = None,
    ) -> T:
        """Call `fn()`, retrying with backoff on any exception in `retry_on`.

        `on_retry(attempt, error, delay)` is called before each sleep — wire
        it to a logger or a metrics counter. Re-raises the last error once
        `max_attempts` is exhausted.
        """
        attempt = 0
        while True:
            try:
                return await fn()
            except retry_on as exc:  # noqa: BLE001 -- caller controls the tuple
                if self.max_attempts is not None and attempt >= self.max_attempts - 1:
                    raise
                delay = self.delay_for(attempt)
                if on_retry is not None:
                    on_retry(attempt, exc, delay)
                await asyncio.sleep(delay)
                attempt += 1
