"""The vocabulary both scenarios speak — defined once, imported everywhere.

If a backend needs a new field on an event, a camera, or the wire envelope,
it goes here first. Never redeclare these shapes locally in a backend repo:
that is exactly the drift this package exists to prevent.
"""

from .camera import CameraRef, Credentials, StreamProfile
from .envelope import Envelope, PayloadKind
from .errors import AttemptedFrom, ReachabilityError, ReachabilityErrorKind
from .detection import (
    BathroomSettings, DetectionSettings, FallSettings, NocturnalSettings, Point,
    StillnessSettings, Zone, ZoneKind,
)
from .events import DEFAULT_SEVERITY, ClipRef, EventKind, FallEvent, Heartbeat, Severity, default_severity
from .control import (
    AgentCapabilityReport, AgentClaimStatus, AgentHealthState, AgentPlatform,
    AgentSetupStatus, AgentStatus, CameraRequestMetadata, ClaimStatus,
    CommandFailureReason, CommandReceipt, CommandResult, CommandState,
    CommandType, ControlCommand, DiscoveredCameraResult, InferenceMode,
    InferenceSelection,
)

__all__ = [
    "CameraRef",
    "Credentials",
    "StreamProfile",
    "Envelope",
    "PayloadKind",
    "AttemptedFrom",
    "ReachabilityError",
    "ReachabilityErrorKind",
    "ClipRef",
    "EventKind",
    "FallEvent",
    "Heartbeat",
    "Severity",
    "DEFAULT_SEVERITY",
    "default_severity",
    "BathroomSettings",
    "DetectionSettings",
    "FallSettings",
    "NocturnalSettings",
    "Point",
    "StillnessSettings",
    "Zone",
    "ZoneKind",
    "AgentCapabilityReport",
    "AgentClaimStatus",
    "AgentHealthState",
    "AgentPlatform",
    "AgentSetupStatus",
    "AgentStatus",
    "CameraRequestMetadata",
    "ClaimStatus",
    "CommandFailureReason",
    "CommandReceipt",
    "CommandResult",
    "CommandState",
    "CommandType",
    "ControlCommand",
    "DiscoveredCameraResult",
    "InferenceMode",
    "InferenceSelection",
]
