"""Model artifacts a detector may load, pinned by SHA-256.

`fixtures/model_artifacts.json` is the single list of expected files, sizes
and hashes. Every agent verifies each file against it before handing the
path to a runtime: the Python agent here, the Android agent against its own
copy of the same manifest. A file that is missing, truncated, or different
by one byte is never loaded.

Schema version 2 (plan Phase 6 step 3) adds, on every entry, `licence`,
`training_data` (dataset ids and tiers; empty for files not trained here) and
`lineage` (every pretraining set and initialisation checkpoint, and where the
file comes from). A manifest of another version, or an entry without these
fields, is refused.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

MANIFEST_RESOURCE = "fixtures/model_artifacts.json"
POSE_MODEL = "pose_landmarker_lite.task"
FALL_CLASSIFIER = "fall_classifier.onnx"
FALL_CLASSIFIER_META = "fall_classifier.onnx.json"
BENCHMARK_FRAME = "benchmark_person.jpg"
SCHEMA_VERSION = 2
PROVENANCE_FIELDS = ("licence", "training_data", "lineage")


class ArtifactError(RuntimeError):
    """A model artifact is missing or does not match the pinned manifest."""


@dataclass(frozen=True)
class Artifact:
    name: str
    sha256: str
    size: int
    licence: str = ""
    training_data: dict = field(default_factory=dict, compare=False)
    lineage: dict = field(default_factory=dict, compare=False)


def manifest() -> dict[str, Artifact]:
    data = json.loads(resources.files("mantau_core.detection")
                      .joinpath(MANIFEST_RESOURCE).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactError(f"model artifact manifest is schema version "
                            f"{data.get('schema_version')}, expected {SCHEMA_VERSION}")
    pinned = {}
    for name, entry in data["artifacts"].items():
        missing = [key for key in PROVENANCE_FIELDS if key not in entry]
        if missing:
            raise ArtifactError(f"{name} has no {', '.join(missing)} in the manifest")
        pinned[name] = Artifact(name, entry["sha256"], int(entry["bytes"]),
                                entry["licence"], entry["training_data"], entry["lineage"])
    return pinned


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
