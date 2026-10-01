"""Package locally trusted recovered components as a limited demo bundle.

This utility intentionally labels the result as genuine demo inference only.  It
does not claim that the recovered components are cryptographically linked to any
historical metric report, training split, or calibration procedure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.artifacts.bundle import (  # noqa: E402
    ModelBundle,
    load_model_bundle,
    save_model_bundle,
    sha256_file,
)
from src.preprocessing.feature_config import ALL_FEATURES  # noqa: E402

MODEL_VERSION = "recovered-xgboost-20260624-demo-v1"
OPERATING_THRESHOLD = 0.53
_SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _require_regular_file(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file.")
    return resolved


def _normalised_transformed_features(preprocessor: Any) -> list[str]:
    if not hasattr(preprocessor, "get_feature_names_out"):
        raise ValueError("Recovered preprocessor must expose get_feature_names_out().")
    return [str(name).split("__")[-1] for name in preprocessor.get_feature_names_out()]


def validate_recovered_components(preprocessor: Any, model: Any) -> None:
    """Confirm recovered components meet SecureSwipe's immutable input contract."""
    expected_count = len(ALL_FEATURES)
    for label, component in (("preprocessor", preprocessor), ("model", model)):
        if int(getattr(component, "n_features_in_", -1)) != expected_count:
            raise ValueError(f"Recovered {label} must expect {expected_count} features.")

    raw_features = getattr(preprocessor, "feature_names_in_", None)
    if raw_features is None:
        raise ValueError("Recovered preprocessor must expose feature_names_in_.")
    raw_names = [str(name) for name in raw_features]
    if len(raw_names) != expected_count or set(raw_names) != set(ALL_FEATURES):
        raise ValueError("Recovered preprocessor raw feature set must equal ALL_FEATURES.")

    model_features = getattr(model, "feature_names_in_", None)
    if model_features is None:
        raise ValueError("Recovered model must expose feature_names_in_.")
    model_names = [str(name) for name in model_features]
    transformed_names = _normalised_transformed_features(preprocessor)
    if len(transformed_names) != expected_count or transformed_names != model_names:
        raise ValueError(
            "Recovered preprocessor transformed feature order must match model.feature_names_in_."
        )

    if np.asarray(getattr(model, "classes_", [])).tolist() != [0, 1]:
        raise ValueError("Recovered model classes_ must be exactly [0, 1].")


def _validate_source_repository(source_repository_url: str, source_repository_sha: str) -> None:
    parsed = urlparse(source_repository_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source_repository_url must be an absolute HTTP(S) URL.")
    if not _SOURCE_SHA_PATTERN.fullmatch(source_repository_sha):
        raise ValueError("source_repository_sha must be a 40-character lowercase Git SHA.")


def _write_recovery_provenance(
    manifest_path: Path,
    *,
    model_path: Path,
    preprocessor_path: Path,
    source_csv_path: Path,
    model_sha256: str,
    preprocessor_sha256: str,
    source_csv_sha256: str,
    source_repository_url: str,
    source_repository_sha: str,
) -> None:
    """Append recovery limitations without changing core bundle verification rules."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["recovery_provenance"] = {
        "evidence_category": "genuine_demo_inference",
        "metric_linkage": "unverified",
        "historical_metrics_claimed": False,
        "threshold_provenance": {
            "value": OPERATING_THRESHOLD,
            "source": "historical validation-selected threshold",
            "recovered_component_linkage": "unverified",
            "purpose": "demo human-review policy only",
            "calibrated": False,
            "cost_optimal": False,
            "razorpay_approved": False,
            "production_approved": False,
        },
        "component_sources": {
            "model": {"filename": model_path.name, "sha256": model_sha256},
            "preprocessor": {
                "filename": preprocessor_path.name,
                "sha256": preprocessor_sha256,
            },
        },
        "component_hash_scope": (
            "SHA-256 hashes establish component identity, not independent authenticity."
        ),
        "source_dataset": {
            "filename": source_csv_path.name,
            "sha256": source_csv_sha256,
            "fingerprint_scope": (
                "Identifies the recovered source dataset, not an exact cryptographically "
                "preserved training split."
            ),
        },
        "source_repository": {
            "url": source_repository_url,
            "sha": source_repository_sha,
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def package_recovered_demo_bundle(
    *,
    model_path: Path,
    preprocessor_path: Path,
    source_csv_path: Path,
    output_dir: Path,
    source_repository_url: str,
    source_repository_sha: str,
    acknowledge_trusted_local_joblib: bool = False,
    score_type: str = "raw_score",
) -> Path:
    """Create and round-trip verify a recovered demo bundle in *output_dir*."""
    if not acknowledge_trusted_local_joblib:
        raise ValueError(
            "Explicit acknowledgement of trusted local Joblib inputs is required before "
            "deserialization."
        )
    if score_type != "raw_score":
        raise ValueError("Recovered demo bundles must use the uncalibrated raw_score type.")
    _validate_source_repository(source_repository_url, source_repository_sha)
    model_file = _require_regular_file(model_path, label="model_path")
    preprocessor_file = _require_regular_file(preprocessor_path, label="preprocessor_path")
    source_csv_file = _require_regular_file(source_csv_path, label="source_csv_path")
    model_sha256 = sha256_file(model_file)
    preprocessor_sha256 = sha256_file(preprocessor_file)
    source_csv_sha256 = sha256_file(source_csv_file)

    preprocessor = joblib.load(preprocessor_file)
    model = joblib.load(model_file)
    validate_recovered_components(preprocessor, model)

    bundle = ModelBundle(
        preprocessor=preprocessor,
        model=model,
        calibrator=None,
        operating_threshold=OPERATING_THRESHOLD,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint=source_csv_sha256,
        model_version=MODEL_VERSION,
        score_type="raw_score",
    )
    manifest = save_model_bundle(bundle, output_dir)
    _write_recovery_provenance(
        manifest,
        model_path=model_file,
        preprocessor_path=preprocessor_file,
        source_csv_path=source_csv_file,
        model_sha256=model_sha256,
        preprocessor_sha256=preprocessor_sha256,
        source_csv_sha256=source_csv_sha256,
        source_repository_url=source_repository_url,
        source_repository_sha=source_repository_sha,
    )
    load_model_bundle(manifest, trusted_root=output_dir.parent)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package trusted recovered components as an explicitly limited demo bundle."
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--preprocessor", type=Path, required=True)
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-repository-url", required=True)
    parser.add_argument("--source-repository-sha", required=True)
    parser.add_argument(
        "--acknowledge-trusted-local-joblib",
        action="store_true",
        required=True,
        help=(
            "Acknowledge that Joblib deserialization can execute code and that all inputs "
            "are locally produced, reviewed artifacts."
        ),
    )
    parser.add_argument("--score-type", default="raw_score")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = package_recovered_demo_bundle(
        model_path=args.model,
        preprocessor_path=args.preprocessor,
        source_csv_path=args.source_csv,
        output_dir=args.output,
        source_repository_url=args.source_repository_url,
        source_repository_sha=args.source_repository_sha,
        acknowledge_trusted_local_joblib=args.acknowledge_trusted_local_joblib,
        score_type=args.score_type,
    )
    print(json.dumps({"manifest": str(manifest), "model_version": MODEL_VERSION}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
