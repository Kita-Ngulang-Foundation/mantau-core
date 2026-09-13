"""Classify an FCM HTTP v1 error response — retry it, or prune the token, never both.

Conflating the two is how a push backend quietly rots: a dead token that
keeps getting retried burns quota forever, and a transient 5xx that gets
pruned loses a device permanently over a blip. See Firebase's FCM HTTP v1
error reference for the `error.status` / `error.details[].errorCode` shape
this reads.
"""

from __future__ import annotations

from enum import Enum


class PushErrorKind(str, Enum):
    RETRYABLE = "retryable"        # 5xx, UNAVAILABLE, quota exhaustion -> backoff and retry
    UNREGISTERED = "unregistered"  # the token is dead -> prune it, never retry
    INVALID = "invalid"            # malformed token/request -> a bug, don't blindly retry
    UNKNOWN = "unknown"


class PushDeliveryError(Exception):
    def __init__(self, kind: PushErrorKind, detail: str) -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind.value}: {detail}")


def classify_fcm_error(status_code: int, body: dict) -> PushErrorKind:
    error = (body or {}).get("error", {})
    status = error.get("status", "")
    details = error.get("details") or []
    error_codes = {d.get("errorCode") for d in details if isinstance(d, dict)}

    if "UNREGISTERED" in error_codes:
        return PushErrorKind.UNREGISTERED
    if status == "INVALID_ARGUMENT" or "INVALID_ARGUMENT" in error_codes:
        return PushErrorKind.INVALID
    if status_code == 429 or status_code >= 500 or status in {"UNAVAILABLE", "INTERNAL", "RESOURCE_EXHAUSTED"}:
        return PushErrorKind.RETRYABLE
    return PushErrorKind.UNKNOWN
