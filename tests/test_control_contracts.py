import json
from pathlib import Path

import mantau_core
from mantau_core.contracts import (
    AgentCapabilityReport, AgentStatus, CameraRequestMetadata, ClaimStatus,
    CommandResult, ControlCommand, DiscoveredCameraResult, InferenceSelection,
)


FIXTURES = Path(mantau_core.__file__).parent / "contracts" / "fixtures" / "v1"
MODELS = {
    "capability_report.json": AgentCapabilityReport,
    "agent_status.json": AgentStatus,
    "command.json": ControlCommand,
    "command_result.json": CommandResult,
    "discovery_result.json": DiscoveredCameraResult,
    "camera_request_metadata.json": CameraRequestMetadata,
    "inference_selection.json": InferenceSelection,
    "claim_status.json": ClaimStatus,
}


def test_v1_control_fixtures_are_exact_round_trips_and_secret_free():
    forbidden = ("password", "agent_secret", "private_key", "rtsp://", "credentials")
    for name, model in MODELS.items():
        raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        parsed = model.model_validate(raw)
        assert parsed.model_dump(mode="json") == raw
        lowered = json.dumps(raw).lower()
        assert all(word not in lowered for word in forbidden)
