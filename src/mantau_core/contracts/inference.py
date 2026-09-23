"""Server inference, version 1: agents that cannot (or are told not to) run
the fall detector upload sampled frames, the server runs the same detector.

Wire format of `POST /agents/{agent_id}/inference`:

- Body: one JPEG (`Content-Type: image/jpeg`), at most the server's
  `max_frame_bytes` (the same size discipline as live-view frames).
- Headers (all required unless noted):
    X-Mantau-Agent        the enrolled agent id (must equal the path id)
    X-Mantau-Camera       camera id, bound to that agent
    X-Mantau-Session      random id per agent run; the server keeps one
                          detector (tracking state) per agent+camera+session
    X-Mantau-Frame        unique frame id -- the idempotency key
    X-Mantau-Frame-Ts     stream-relative capture time in ms, strictly
                          increasing within a session (the detector's clock)
    X-Mantau-Captured-At  capture wall-clock time, Unix ms; frames older than
                          the server's `max_frame_age_s` are rejected
    X-Mantau-Event-Ids    optional, comma-separated: HYBRID confirmation of
                          events the agent already detected and sent
    X-Mantau-Signature    hex HMAC-SHA256 of `signing_message(...)` with the
                          agent's enrolled secret

Semantics the adapters rely on:

- Authentication: the same per-agent secret as `/ingest`, live frames and
  recordings, but a distinct, versioned message prefix so a signature from
  one endpoint can never be replayed at another.
- Idempotency: a retry with the same frame id returns the stored result
  without running the detector again (for `idempotency_ttl_s`).
- Ordering: a frame whose `ts_ms` does not increase within its session is
  answered with `processed=false, reason="out_of_order"`; frames are
  disposable and are never reordered or queued.
- Correlation: events the server detects are stored and alerted through the
  normal event path under the uploading agent, and returned here so the agent
  can attach clips. Confirmation results for `event_ids` are stored against
  those events (only events of the uploading agent) and returned here.
- Retention: frames are decoded in memory, run through the detector and
  dropped; no frame is ever written to disk. Only results (events,
  confirmations) are stored, under the same retention as events.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .events import FallEvent

SIGNING_PREFIX = b"mantau-inference-v1"
MAX_EVENT_IDS = 8


class InferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1


class InferenceCapability(InferenceModel):
    """`GET /inference/capability`: whether this server runs the detector."""

    available: bool
    detector: str | None = None
    max_frame_bytes: int = Field(ge=1)
    max_frame_age_s: float = Field(gt=0)
    max_fps: float = Field(gt=0)
    reason: str | None = None


class InferenceConfirmation(InferenceModel):
    """The server's independent look at an event the agent detected: is a
    person lying down in the confirmation frame?"""

    event_id: str
    confirmed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str | None = None


class InferenceResult(InferenceModel):
    frame_id: str
    session_id: str
    processed: bool
    duplicate: bool = False
    reason: str | None = None
    events: list[FallEvent] = Field(default_factory=list)
    confirmations: list[InferenceConfirmation] = Field(default_factory=list)
    people: int | None = None
    server_ms: float = Field(default=0.0, ge=0.0)


def signing_message(*, agent_id: str, camera_id: str, session_id: str, frame_id: str,
                    ts_ms: int, captured_at_ms: int, event_ids: tuple[str, ...] | list[str],
                    body: bytes) -> bytes:
    """Canonical bytes the signature covers: every header that changes the
    meaning of the request, then the frame itself."""
    fields = (agent_id, camera_id, session_id, frame_id, str(int(ts_ms)),
              str(int(captured_at_ms)), ",".join(event_ids))
    return SIGNING_PREFIX + b"\n" + "\n".join(fields).encode("utf-8") + b"\n" + body


def sign(secret: str, **fields) -> str:
    return hmac.new(secret.encode("utf-8"), signing_message(**fields), hashlib.sha256).hexdigest()


def verify(secret: str, signature: str, **fields) -> bool:
    return hmac.compare_digest(sign(secret, **fields), signature)
