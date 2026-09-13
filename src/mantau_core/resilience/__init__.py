"""Reconnect logic used identically by an RTSP puller and a tunnel client.

`mantau-ai`'s `RTSPSource` today reconnects on a flat `time.sleep(0.5)` — no
backoff, no jitter. Both backends replace that call site with `backoff` from
here, and wrap any long-running connection loop (RTSP pull, tunnel uplink)
in a `Supervisor` so a failure restarts it instead of killing the process.
"""

from .backoff import BackoffPolicy, compute_delay
from .supervisor import RestartBudgetExhausted, Supervisor, SupervisorStatus

__all__ = [
    "BackoffPolicy",
    "compute_delay",
    "Supervisor",
    "SupervisorStatus",
    "RestartBudgetExhausted",
]
