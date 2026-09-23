"""Model artifacts are verified against pinned SHA-256 values before loading."""

import json
from importlib import resources

import pytest

from mantau_core.detection import artifacts
from mantau_core.detection.artifacts import ArtifactError


def _write_pinned(tmp_path, name: str, content: bytes, monkeypatch):
    import hashlib
    (tmp_path / name).write_bytes(content)
    pinned = {name: artifacts.Artifact(name, hashlib.sha256(content).hexdigest(), len(content))}
    monkeypatch.setattr(artifacts, "manifest", lambda: pinned)


def test_manifest_pins_every_model_file():
    pinned = artifacts.manifest()
    assert set(pinned) == {artifacts.POSE_MODEL, artifacts.FALL_CLASSIFIER,
                           artifacts.FALL_CLASSIFIER_META, artifacts.BENCHMARK_FRAME}
    for artifact in pinned.values():
        assert len(artifact.sha256) == 64 and int(artifact.sha256, 16) >= 0
        assert artifact.size > 0


def test_manifest_ships_with_the_package():
    raw = resources.files("mantau_core.detection").joinpath(artifacts.MANIFEST_RESOURCE)
    assert json.loads(raw.read_text(encoding="utf-8"))["schema_version"] == 1


def test_matching_file_verifies(tmp_path, monkeypatch):
    _write_pinned(tmp_path, "m.bin", b"model-bytes", monkeypatch)
    assert artifacts.verify(tmp_path) == {"m.bin": tmp_path / "m.bin"}


def test_tampered_file_is_rejected(tmp_path, monkeypatch):
    _write_pinned(tmp_path, "m.bin", b"model-bytes", monkeypatch)
    (tmp_path / "m.bin").write_bytes(b"model-bytez")  # same size, one byte differs
    with pytest.raises(ArtifactError, match="does not match"):
        artifacts.verify(tmp_path)


def test_truncated_file_is_rejected(tmp_path, monkeypatch):
    _write_pinned(tmp_path, "m.bin", b"model-bytes", monkeypatch)
    (tmp_path / "m.bin").write_bytes(b"model")
    with pytest.raises(ArtifactError, match="does not match"):
        artifacts.verify(tmp_path)


def test_missing_file_is_rejected(tmp_path, monkeypatch):
    _write_pinned(tmp_path, "m.bin", b"model-bytes", monkeypatch)
    (tmp_path / "m.bin").unlink()
    with pytest.raises(ArtifactError, match="not found"):
        artifacts.verify(tmp_path)


def test_unpinned_name_is_rejected(tmp_path):
    with pytest.raises(ArtifactError, match="not a pinned"):
        artifacts.verify(tmp_path, ("anything.bin",))
