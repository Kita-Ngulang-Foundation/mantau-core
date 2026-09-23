"""Server-inference wire contract v1: signatures and result shapes.

The golden fixtures are shared with the Android agent's tests, so both
signers must produce the recorded signature byte for byte.
"""

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest

import mantau_core
from mantau_core.contracts import InferenceCapability, InferenceResult
from mantau_core.contracts import inference

FIXTURES = Path(mantau_core.__file__).parent / "contracts" / "fixtures" / "v1"


def _request() -> tuple[dict, bytes, str, str]:
    raw = json.loads((FIXTURES / "inference_request.json").read_text(encoding="utf-8"))
    fields = {k: raw[k] for k in ("agent_id", "camera_id", "session_id", "frame_id",
                                   "ts_ms", "captured_at_ms", "event_ids")}
    return fields, base64.b64decode(raw["body_base64"]), raw["test_secret"], raw["signature"]


def test_golden_signature():
    fields, body, secret, signature = _request()
    assert inference.sign(secret, body=body, **fields) == signature
    assert inference.verify(secret, signature, body=body, **fields)


@pytest.mark.parametrize("field,value", [
    ("agent_id", "agent-8"), ("camera_id", "cam-2"), ("session_id", "other"),
    ("frame_id", "a1b2c3d5"), ("ts_ms", 12346), ("captured_at_ms", 1790000000124),
    ("event_ids", ["e1"]),
])
def test_every_signed_field_matters(field, value):
    fields, body, secret, signature = _request()
    assert not inference.verify(secret, signature, body=body, **{**fields, field: value})


def test_body_and_secret_matter():
    fields, body, secret, signature = _request()
    assert not inference.verify(secret, signature, body=body + b"x", **fields)
    assert not inference.verify("other-secret", signature, body=body, **fields)


def test_live_frame_signature_cannot_be_replayed_as_inference():
    fields, body, secret, _ = _request()
    frame_signature = hmac.new(secret.encode(), fields["camera_id"].encode() + b"." + body,
                               hashlib.sha256).hexdigest()
    assert not inference.verify(secret, frame_signature, body=body, **fields)


@pytest.mark.parametrize("name,model", [
    ("inference_result.json", InferenceResult),
    ("inference_capability.json", InferenceCapability),
])
def test_fixtures_round_trip(name, model):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert model.model_validate(raw).model_dump(mode="json") == raw
    assert "secret" not in json.dumps(raw).lower()
