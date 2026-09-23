"""Version 1 control-plane wire contracts shared by server and agents.

These models deliberately contain operational metadata only. Credentials and
enrollment secrets belong to the encrypted delivery layer, never to status or
result objects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from urllib.parse import parse_qsl, urlsplit


class ControlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    schema_version: Literal[1] = 1


class AgentPlatform(str, Enum):
    LINUX_X86_64 = "linux_x86_64"
    LINUX_ARM64 = "linux_arm64"
    RASPBERRY_PI = "raspberry_pi"
    ANDROID = "android"
    OTHER = "other"


class AgentSetupStatus(str, Enum):
    NOT_STARTED = "not_started"
    WAITING_FOR_AGENT = "waiting_for_agent"
    DISCOVERING = "discovering"
    CONFIGURING_CAMERA = "configuring_camera"
    SELECTING_MODE = "selecting_mode"
    ACTIVE = "active"
    FAILED = "failed"


class AgentHealthState(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    STOPPED = "stopped"


class AgentClaimStatus(str, Enum):
    UNCLAIMED = "unclaimed"
    PENDING = "pending"
    CLAIMED = "claimed"


class InferenceMode(str, Enum):
    AUTO = "AUTO"
    EDGE = "EDGE"
    CLOUD = "CLOUD"
    HYBRID = "HYBRID"


class CommandType(str, Enum):
    DISCOVER = "discover"
    CAMERA_TEST = "camera_test"
    CONFIGURE_CAMERA = "configure_camera"
    SET_INFERENCE_MODE = "set_inference_mode"
    RESTART = "restart"
    RECONFIGURE = "reconfigure"
    # Payload: {"camera_id": ..., "settings": DetectionSettings JSON}.
    APPLY_DETECTION_SETTINGS = "apply_detection_settings"


class CommandState(str, Enum):
    QUEUED = "queued"
    DELIVERED = "delivered"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class CommandFailureReason(str, Enum):
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED = "unsupported"
    CAMERA_UNREACHABLE = "camera_unreachable"
    AUTHENTICATION_FAILED = "authentication_failed"
    CONFIGURATION_FAILED = "configuration_failed"
    EXECUTION_FAILED = "execution_failed"
    EXPIRED = "expired"


class AgentCapabilityReport(ControlModel):
    platform: AgentPlatform
    architecture: str
    cpu: str
    memory_bytes: int | None = Field(default=None, ge=0)
    available_accelerators: list[str] = Field(default_factory=list)
    supported_detector_backends: list[str] = Field(default_factory=list)
    software_version: str
    recommended_mode: InferenceMode
    supported_inference_modes: list[InferenceMode] = Field(default_factory=list)
    recommendation_reason: str | None = None


class AgentStatus(ControlModel):
    agent_id: str
    name: str
    platform: AgentPlatform | None = None
    claim_status: AgentClaimStatus
    setup_status: AgentSetupStatus
    health_state: AgentHealthState
    requested_inference_mode: InferenceMode | None = None
    effective_inference_mode: InferenceMode | None = None
    capabilities: AgentCapabilityReport | None = None
    camera_connectivity: Literal["connected", "disconnected", "unknown"] = "unknown"
    last_heartbeat_at: datetime | None = None
    last_frame_at: datetime | None = None
    health_explanation: str | None = None


class ClaimStatus(ControlModel):
    agent_id: str
    status: AgentClaimStatus
    claimed_at: datetime | None = None


class CameraRequestMetadata(ControlModel):
    camera_id: str = "cam-1"
    name: str
    host: str
    port: int = Field(default=554, ge=1, le=65535)
    main_path: str = "/stream1"
    sub_path: str | None = None
    username_present: bool = False

    @field_validator("host")
    @classmethod
    def host_has_no_credentials(cls, value: str) -> str:
        if not value or any(c in value for c in ("@", "/", "?", "#")) or any(c.isspace() for c in value):
            raise ValueError("Use a hostname or IP without a URL or credentials")
        return value

    @field_validator("main_path", "sub_path")
    @classmethod
    def path_has_no_credentials(cls, value: str | None) -> str | None:
        if value is None:
            return value
        parsed = urlsplit(value)
        sensitive = {"user", "username", "password", "passwd", "pwd", "token", "auth", "authorization"}
        if (not value.startswith("/") or parsed.netloc or parsed.scheme
                or any(key.lower() in sensitive for key, _ in parse_qsl(parsed.query))):
            raise ValueError("Use a stream path with credentials in the separate fields")
        return value


class DiscoveredCameraResult(ControlModel):
    host: str
    name: str | None = None
    port: int = Field(default=554, ge=1, le=65535)
    main_path: str = "/stream1"
    sub_path: str | None = None
    rtsp_reachable: bool
    failure_reason: str | None = None


class InferenceSelection(ControlModel):
    requested_mode: InferenceMode
    effective_mode: InferenceMode
    reason: str | None = None


class ControlCommand(ControlModel):
    command_id: str
    command_type: CommandType
    state: CommandState
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    expires_at: datetime


class CommandReceipt(ControlModel):
    command_id: str
    accepted: bool
    state: CommandState = CommandState.QUEUED


class CommandResult(ControlModel):
    command_id: str
    state: CommandState
    failure_reason: CommandFailureReason | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    completed_at: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
