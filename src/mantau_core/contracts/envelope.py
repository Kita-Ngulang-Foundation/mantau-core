"""The wire format for Scenario 2's uplink: agent -> server, over the tunnel.

`seq` is what makes the server's ingest layer able to dedupe a retried send
(the agent's local spool will retry after a dropped tunnel) and detect
out-of-order delivery after an outage — it must be monotonically increasing
per `agent_id`, assigned once by the agent and never reused.

Signing is HMAC-SHA256 over a canonical (sorted-keys) JSON encoding of every
field except `sig` itself, using a secret the agent was enrolled with. This
is deliberately simple (no mTLS, no JWT) — enough to let the server reject a
forged sender without adding a certificate authority to a weekend prototype.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .events import FallEvent, Heartbeat


class PayloadKind(str, Enum):
    FALL_EVENT = "fall_event"
    HEARTBEAT = "heartbeat"


class Envelope(BaseModel):
    agent_id: str
    seq: int
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    kind: PayloadKind
    payload: dict
    sig: str = ""  # populated by .sign(); empty means unsigned

    @classmethod
    def for_event(cls, agent_id: str, seq: int, event: FallEvent) -> "Envelope":
        # zone_id is left out when empty so fall payloads stay byte-identical to
        # agents that predate it (the signature covers the payload as sent).
        payload = event.model_dump(mode="json", exclude={"zone_id"} if event.zone_id is None else None)
        return cls(agent_id=agent_id, seq=seq, kind=PayloadKind.FALL_EVENT, payload=payload)

    @classmethod
    def for_heartbeat(cls, agent_id: str, seq: int, heartbeat: Heartbeat) -> "Envelope":
        return cls(agent_id=agent_id, seq=seq, kind=PayloadKind.HEARTBEAT,
                    payload=heartbeat.model_dump(mode="json"))

    def event(self) -> FallEvent:
        if self.kind is not PayloadKind.FALL_EVENT:
            raise ValueError(f"envelope carries {self.kind}, not a fall event")
        return FallEvent.model_validate(self.payload)

    def heartbeat(self) -> Heartbeat:
        if self.kind is not PayloadKind.HEARTBEAT:
            raise ValueError(f"envelope carries {self.kind}, not a heartbeat")
        return Heartbeat.model_validate(self.payload)

    def _canonical_bytes(self) -> bytes:
        """Deterministic bytes for signing — every field except `sig`."""
        fields = self.model_dump(mode="json", exclude={"sig"})
        return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def sign(self, secret: str) -> "Envelope":
        """Return a copy of this envelope with `sig` computed from `secret`."""
        digest = hmac.new(secret.encode("utf-8"), self._canonical_bytes(), hashlib.sha256)
        return self.model_copy(update={"sig": digest.hexdigest()})

    def verify(self, secret: str) -> bool:
        """True if `sig` matches what this envelope's contents hash to under `secret`."""
        if not self.sig:
            return False
        expected = hmac.new(secret.encode("utf-8"), self._canonical_bytes(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.sig)
