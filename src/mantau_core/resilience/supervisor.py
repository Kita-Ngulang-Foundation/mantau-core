"""Run a long-lived task, restart it on failure, notice when it's flapping.

This is the shape both an RTSP puller (Scenario 1: `workers/pool.py`) and an
agent's camera/uplink loop (Scenario 2) need: keep the connection alive
across transient failures, but stop and surface the problem — rather than
spin silently forever — if it is failing far faster than backoff can help.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .backoff import BackoffPolicy


class RestartBudgetExhausted(RuntimeError):
    """The supervised task failed too many times, too fast — stop, don't spin."""


@dataclass
class SupervisorStatus:
    name: str
    running: bool
    restarts: int
    last_error: str | None
    last_started_at: datetime | None


class Supervisor:
    def __init__(
        self,
        name: str,
        task_factory: Callable[[], Awaitable[None]],
        *,
        backoff: BackoffPolicy | None = None,
        max_restarts: int = 10,
        window_s: float = 60.0,
    ) -> None:
        self.name = name
        self._task_factory = task_factory
        self._backoff = backoff or BackoffPolicy()
        self._max_restarts = max_restarts
        self._window_s = window_s
        self._restart_times: deque[float] = deque()
        self._restarts_total = 0
        self._last_error: str | None = None
        self._last_started_at: datetime | None = None
        self._running = False

    def status(self) -> SupervisorStatus:
        return SupervisorStatus(
            name=self.name, running=self._running, restarts=self._restarts_total,
            last_error=self._last_error, last_started_at=self._last_started_at,
        )

    def _record_restart(self) -> None:
        now = time.monotonic()
        self._restart_times.append(now)
        while self._restart_times and now - self._restart_times[0] > self._window_s:
            self._restart_times.popleft()
        self._restarts_total += 1

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Run `task_factory()` until it returns cleanly, `stop_event` fires,
        or the restart budget is exhausted.

        A clean return from the task ends supervision on purpose — this
        supervises a *task*, it does not retry a single call.
        """
        attempt = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                self._running = False
                return
            self._running = True
            self._last_started_at = datetime.now(timezone.utc)
            try:
                await self._task_factory()
                self._running = False
                return
            except asyncio.CancelledError:
                self._running = False
                raise
            except Exception as exc:  # noqa: BLE001 -- this IS the restart boundary
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._record_restart()
                if len(self._restart_times) > self._max_restarts:
                    self._running = False
                    raise RestartBudgetExhausted(
                        f"{self.name}: {self._restarts_total} restarts total, "
                        f"{len(self._restart_times)} within the last {self._window_s:.0f}s "
                        f"(budget {self._max_restarts}); last error: {self._last_error}"
                    ) from exc
                delay = self._backoff.delay_for(attempt)
                attempt += 1
                await asyncio.sleep(delay)
