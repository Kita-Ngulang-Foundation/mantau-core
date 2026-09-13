"""Reachability failure taxonomy — shared because it is Scenario 1's data.

Scenario 1 probes a camera from OUR network (the internet); Scenario 2's agent
probes the same camera from the customer's LAN. Same taxonomy, different
`attempted_from` — that difference, tallied over real connection attempts, is
what turns "Indonesian home internet can't port-forward" from a claim in a
document into a ledger you can show your advisor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ReachabilityErrorKind(str, Enum):
    TIMEOUT = "timeout"                    # no response within the connect window
    CONNECTION_REFUSED = "connection_refused"  # reached a host, nothing listening
    AUTH_FAILED = "auth_failed"            # RTSP 401/403 — reachable, wrong creds
    DNS_FAILURE = "dns_failure"            # hostname didn't resolve
    CGNAT_SUSPECTED = "cgnat_suspected"    # times out AND the WAN IP is a shared/carrier range
    TUNNEL_DOWN = "tunnel_down"            # Scenario 2 only — the agent's uplink itself is down
    UNKNOWN = "unknown"


class AttemptedFrom(str, Enum):
    INTERNET = "internet"  # Scenario 1: our backend, reaching in from outside the LAN
    LAN = "lan"            # Scenario 2: the agent, reaching the camera locally


class ReachabilityError(BaseModel):
    camera_id: str
    kind: ReachabilityErrorKind
    attempted_from: AttemptedFrom
    detail: str = ""
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
