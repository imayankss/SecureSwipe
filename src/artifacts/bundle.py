"""Integrity and provenance controls for locally produced model bundles.

Joblib/pickle formats can execute code during deserialization. SHA-256 detects
corruption and unexpected replacement; it does not make arbitrary pickle input
safe. These functions therefore only load server-configured artifacts under an
explicit trusted local root and never accept API-supplied paths or bytes.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence, cast

import joblib

from src.preprocessing.feature_config import ALL_FEATURES

BUNDLE_FORMAT_VERSION = "1"
MANIFEST_FILENAME = "manifest.json"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_PACKAGES = ("joblib", "numpy", "pandas", "scikit-learn")
ScoreType = Literal["raw_score", "calibrated_probability"]


class ArtifactVerificationError(RuntimeError):
    """Raised when an artifact fails trust checks."""


@dataclass(frozen=True)
class ModelBundle:
    """A fitted preprocessing/model unit plus its serving contract."""

    preprocessor: Any
    model: Any
    calibrator: Any | None
    operating_threshold: float
    feature_schema: tuple[str, ...]
    training_data_fingerprint: str
    model_version: str
    score_type: ScoreType = "raw_score"

    def validate(self) -> None:
        if self.preprocessor is None or not hasattr(self.preprocessor, "transform"):
            raise ValueError("ModelBundle preprocessor must expose transform().")
        if self.model is None or not hasattr(self.model, "predict_proba"):
            raise ValueError("ModelBundle model must expose predict_proba().")
        if self.calibrator is not None and not (
            hasattr(self.calibrator, "predict_proba") or hasattr(self.calibrator, "predict")
        ):
            raise ValueError("ModelBundle calibrator must expose predict() or predict_proba().")
        if not 0.0 <= float(self.operating_threshold) <= 1.0:
            raise ValueError("ModelBundle operating_threshold must be in [0, 1].")
        if tuple(self.feature_schema) != tuple(ALL_FEATURES):
            raise ValueError("ModelBundle feature_schema must match the canonical ordered schema.")
        if not _SHA256_PATTERN.fullmatch(self.training_data_fingerprint):
            raise ValueError("ModelBundle training_data_fingerprint must be a SHA-256 digest.")
        if not self.model_version.strip():
            raise ValueError("ModelBundle model_version must not be empty.")
        if self.score_type not in {"raw_score", "calibrated_probability"}:
            raise ValueError("Unsupported ModelBundle score_type.")
        if self.calibrator is None and self.score_type != "raw_score":
            raise ValueError("A bundle without a calibrator must expose raw_score.")
        if self.calibrator is not None and self.score_type != "calibrated_probability":
            raise ValueError("A bundle with a calibrator must expose calibrated_probability.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_trusted_path(path: str | Path, trusted_root: str | Path) -> Path:
    root = Path(trusted_root).expanduser().resolve(strict=True)
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        working_directory_candidate = candidate.resolve(strict=False)
        candidate = (
            working_directory_candidate
            if working_directory_candidate.exists()
            else root / candidate
        )
    if candidate.is_symlink():
        raise ArtifactVerificationError("Artifact must not be a symbolic link.")
    candidate = candidate.resolve(strict=True)
    if not candidate.is_relative_to(root):
        raise ArtifactVerificationError(
            f"Artifact path '{candidate}' is outside trusted root '{root}'."
        )
    if not candidate.is_file():
        raise ArtifactVerificationError("Artifact must be a regular file.")
    return candidate


def _checksum_sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def write_checksum_sidecar(path: str | Path) -> Path:
    """Write a deterministic checksum sidecar for a locally produced artifact."""
    artifact = Path(path).resolve(strict=True)
    digest = sha256_file(artifact)
    sidecar = _checksum_sidecar(artifact)
    sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="ascii")
    return sidecar


def _read_expected_checksum(sidecar: Path, artifact_name: str) -> str:
    if not sidecar.is_file():
        raise ArtifactVerificationError(f"Missing checksum sidecar: {sidecar}.")
    parts = sidecar.read_text(encoding="ascii").strip().split()
    if len(parts) != 2 or parts[1] != artifact_name or not _SHA256_PATTERN.fullmatch(parts[0]):
        raise ArtifactVerificationError(f"Malformed checksum sidecar: {sidecar}.")
    return parts[0]


def load_verified_joblib(
    path: str | Path,
    *,
    trusted_root: str | Path,
    required_attributes: Sequence[str] = (),
) -> Any:
    """Verify a trusted local joblib artifact before deserializing it."""
    artifact = _resolve_trusted_path(path, trusted_root)
    if artifact.suffix != ".joblib":
        raise ArtifactVerificationError("Only .joblib artifacts are accepted.")
    expected = _read_expected_checksum(_checksum_sidecar(artifact), artifact.name)
    actual = sha256_file(artifact)
    if actual != expected:
        raise ArtifactVerificationError(
            f"Checksum mismatch for '{artifact.name}': expected {expected}, got {actual}."
        )

    loaded = joblib.load(artifact)
    missing = [name for name in required_attributes if not hasattr(loaded, name)]
    if missing:
        raise ArtifactVerificationError(
            f"Verified artifact payload is missing required attributes: {missing}."
        )
    return loaded


def _runtime_versions() -> dict[str, str]:
    return {package: metadata.version(package) for package in _RUNTIME_PACKAGES}


def _artifact_entry(path: Path, payload: Any) -> dict[str, Any]:
    return {
        "filename": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "python_type": f"{type(payload).__module__}.{type(payload).__qualname__}",
    }


def save_model_bundle(bundle: ModelBundle, output_dir: str | Path) -> Path:
    """Persist a complete versioned bundle and return its manifest path."""
    bundle.validate()
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)

    payloads: dict[str, Any] = {"preprocessor": bundle.preprocessor, "model": bundle.model}
    if bundle.calibrator is not None:
        payloads["calibrator"] = bundle.calibrator

    artifacts: dict[str, dict[str, Any]] = {}
    for name, payload in payloads.items():
        artifact_path = directory / f"{name}.joblib"
        joblib.dump(payload, artifact_path)
        write_checksum_sidecar(artifact_path)
        artifacts[name] = _artifact_entry(artifact_path, payload)

    manifest = {
        "bundle_format_version": BUNDLE_FORMAT_VERSION,
        "model_version": bundle.model_version,
        "operating_threshold": float(bundle.operating_threshold),
        "score_type": bundle.score_type,
        "feature_schema": list(bundle.feature_schema),
        "training_data_fingerprint": bundle.training_data_fingerprint,
        "runtime": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "dependencies": _runtime_versions(),
        },
        "artifacts": artifacts,
    }
    manifest_path = directory / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    required = {
        "bundle_format_version",
        "model_version",
        "operating_threshold",
        "score_type",
        "feature_schema",
        "training_data_fingerprint",
        "runtime",
        "artifacts",
    }
    missing = required - manifest.keys()
    if missing:
        raise ArtifactVerificationError(f"Bundle manifest is missing fields: {sorted(missing)}.")
    if manifest["bundle_format_version"] != BUNDLE_FORMAT_VERSION:
        raise ArtifactVerificationError("Unsupported bundle_format_version.")
    if manifest["feature_schema"] != list(ALL_FEATURES):
        raise ArtifactVerificationError("Bundle feature schema/order mismatch.")
    if not _SHA256_PATTERN.fullmatch(str(manifest["training_data_fingerprint"])):
        raise ArtifactVerificationError("Invalid training_data_fingerprint.")
    threshold = manifest["operating_threshold"]
    if not isinstance(threshold, (int, float)) or not 0.0 <= float(threshold) <= 1.0:
        raise ArtifactVerificationError("Invalid operating_threshold.")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict) or not {"model", "preprocessor"} <= artifacts.keys():
        raise ArtifactVerificationError("Bundle must contain model and preprocessor artifacts.")
    if manifest["score_type"] == "calibrated_probability" and "calibrator" not in artifacts:
        raise ArtifactVerificationError("Calibrated score_type requires a calibrator artifact.")

    runtime = manifest["runtime"]
    if not isinstance(runtime, dict):
        raise ArtifactVerificationError("Bundle runtime metadata is missing.")
    expected_python = ".".join(str(runtime.get("python", "")).split(".")[:2])
    current_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if expected_python != current_python:
        raise ArtifactVerificationError(
            f"Python runtime mismatch: bundle {expected_python}, current {current_python}."
        )
    dependencies = runtime.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ArtifactVerificationError("Bundle runtime dependencies are missing.")
    for package, current in _runtime_versions().items():
        if dependencies.get(package) != current:
            raise ArtifactVerificationError(
                f"Dependency mismatch for {package}: bundle {dependencies.get(package)!r}, "
                f"current {current!r}."
            )


def load_model_bundle(
    manifest_path: str | Path,
    *,
    trusted_root: str | Path,
) -> ModelBundle:
    """Validate all metadata/checksums, then deserialize trusted payloads."""
    manifest_file = _resolve_trusted_path(manifest_path, trusted_root)
    if manifest_file.name != MANIFEST_FILENAME:
        raise ArtifactVerificationError(f"Expected manifest filename '{MANIFEST_FILENAME}'.")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactVerificationError(f"Invalid bundle manifest: {exc}.") from exc
    if not isinstance(manifest, dict):
        raise ArtifactVerificationError("Bundle manifest must be a JSON object.")
    _validate_manifest(manifest)

    artifacts = manifest["artifacts"]
    for name in ("preprocessor", "model", "calibrator"):
        if name not in artifacts:
            continue
        entry = artifacts[name]
        required_entry = {"filename", "sha256", "size_bytes", "python_type"}
        if not isinstance(entry, dict) or required_entry - entry.keys():
            raise ArtifactVerificationError(f"Incomplete artifact entry for {name}.")
        filename = entry["filename"]
        if filename != f"{name}.joblib" or Path(filename).name != filename:
            raise ArtifactVerificationError(f"Unsafe artifact filename for {name}.")
        artifact = _resolve_trusted_path(manifest_file.parent / filename, trusted_root)
        if artifact.parent != manifest_file.parent:
            raise ArtifactVerificationError("Bundle payload must be colocated with its manifest.")
        if artifact.stat().st_size != entry["size_bytes"]:
            raise ArtifactVerificationError(f"Artifact size mismatch for {name}.")
        if sha256_file(artifact) != entry["sha256"]:
            raise ArtifactVerificationError(f"Artifact checksum mismatch for {name}.")

    loaded: dict[str, Any] = {}
    # No deserialization occurs before every bundle payload has passed verification.
    for name in ("preprocessor", "model", "calibrator"):
        if name in artifacts:
            artifact = manifest_file.parent / artifacts[name]["filename"]
            loaded[name] = joblib.load(artifact)
            actual_type = f"{type(loaded[name]).__module__}.{type(loaded[name]).__qualname__}"
            if actual_type != artifacts[name]["python_type"]:
                raise ArtifactVerificationError(f"Payload type mismatch for {name}.")

    bundle = ModelBundle(
        preprocessor=loaded["preprocessor"],
        model=loaded["model"],
        calibrator=loaded.get("calibrator"),
        operating_threshold=float(manifest["operating_threshold"]),
        feature_schema=tuple(manifest["feature_schema"]),
        training_data_fingerprint=str(manifest["training_data_fingerprint"]),
        model_version=str(manifest["model_version"]),
        score_type=cast(ScoreType, manifest["score_type"]),
    )
    bundle.validate()
    return bundle
