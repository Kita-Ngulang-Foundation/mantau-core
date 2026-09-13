"""The vocabulary both scenarios speak — defined once, imported everywhere.

If a backend needs a new field on an event, a camera, or the wire envelope,
it goes here first. Never redeclare these shapes locally in a backend repo:
that is exactly the drift this package exists to prevent.
"""

from .camera import CameraRef, Credentials, StreamProfile
from .envelope import Envelope
from .errors import ReachabilityError, ReachabilityErrorKind
from .events import ClipRef, EventKind, FallEvent, Heartbeat, Severity

__all__ = [
    "CameraRef",
    "Credentials",
    "StreamProfile",
    "Envelope",
    "ReachabilityError",
    "ReachabilityErrorKind",
    "ClipRef",
    "EventKind",
    "FallEvent",
    "Heartbeat",
    "Severity",
]
