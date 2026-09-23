"""Model artifacts a detector may load, pinned by SHA-256.

`fixtures/model_artifacts.json` is the single list of expected files, sizes
and hashes. Every agent verifies each file against it before handing the
path to a runtime: the Python agent here, the Android agent against its own
copy of the same manifest. A file that is missing, truncated, or different
by one byte is never loaded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

MANIFEST_RESOURCE = "fixtures/model_artifacts.json"
POSE_MODEL = "pose_landmarker_lite.task"
FALL_CLASSIFIER = "fall_classifier.onnx"
FALL_CLASSIFIER_META = "fall_classifier.onnx.json"
BENCHMARK_FRAME = "benchmark_person.jpg"


class ArtifactError(RuntimeError):
    """A model artifact is missing or does not match the pinned manifest."""


@dataclass(frozen=True)
class Artifact:
    name: str
    sha256: str
    size: int


def manifest() -> dict[str, Artifact]:
    data = json.loads(resources.files("mantau_core.detection")
                      .joinpath(MANIFEST_RESOURCE).read_text(encoding="utf-8"))
    return {name: Artifact(name, entry["sha256"], int(entry["bytes"]))
            for name, entry in data["artifacts"].items()}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(directory: str | Path, names: tuple[str, ...] | None = None) -> dict[str, Path]:
    """Check each named artifact in `directory` against the manifest.

    Returns name -> path for every verified file; raises `ArtifactError`
    naming the first file that is missing or differs (never its contents)."""
    pinned = manifest()
    directory = Path(directory)
    verified: dict[str, Path] = {}
    for name in names or tuple(pinned):
        expected = pinned.get(name)
        if expected is None:
            raise ArtifactError(f"{name} is not a pinned model artifact")
        path = directory / name
        if not path.is_file():
            raise ArtifactError(f"model artifact {name} not found in {directory}")
        if path.stat().st_size != expected.size or sha256_file(path) != expected.sha256:
            raise ArtifactError(f"model artifact {name} does not match its pinned SHA-256")
        verified[name] = path
    return verified
