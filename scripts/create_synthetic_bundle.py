"""Create a deterministic synthetic-only bundle for API/container smoke tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.artifacts.bundle import (  # noqa: E402
    ModelBundle,
    data_role_metadata,
    intended_use_metadata,
    save_model_bundle,
    threshold_provenance_metadata,
    training_provenance_metadata,
)
from src.data.data_loader import fingerprint_dataframe
from src.preprocessing.feature_config import ALL_FEATURES, RANDOM_STATE
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor

SYNTHETIC_MODEL_VERSION = "synthetic-smoke-1"
SYNTHETIC_PRODUCER_POLICY = "synthetic_api_smoke_v1"


def synthetic_training_data() -> tuple[pd.DataFrame, np.ndarray]:
    """Return fixed, non-customer data that exercises the canonical schema."""
    row_count = 64
    indices = np.arange(row_count, dtype=float)
    values: dict[str, np.ndarray] = {
        "Time": indices * 17.0,
        "Amount": 1.0 + (indices % 19.0) * 3.25,
    }
    for feature_index in range(1, 29):
        values[f"V{feature_index}"] = (
            np.sin(indices * (feature_index + 1) / 13.0) + feature_index / 100.0
        )
    frame = pd.DataFrame(values, columns=ALL_FEATURES)
    labels = ((indices.astype(int) % 7 == 0) | (indices.astype(int) % 11 == 0)).astype(int)
    return frame, labels


def build_synthetic_bundle() -> tuple[ModelBundle, dict[str, float]]:
    """Fit a deterministic CPU model and return one canonical smoke request."""
    frame, labels = synthetic_training_data()
    preprocessor = fit_preprocessor(frame, build_preprocessor())
    preprocessor.set_output(transform="pandas")
    transformed = preprocessor.transform(frame)
    model = LogisticRegression(random_state=RANDOM_STATE, max_iter=1_000).fit(transformed, labels)
    request = {feature: float(frame.iloc[3][feature]) for feature in ALL_FEATURES}
    labeled_frame = frame.copy()
    labeled_frame["Class"] = labels
    training_fingerprint = fingerprint_dataframe(labeled_frame)
    model_fit = data_role_metadata(
        fingerprint_sha256=training_fingerprint,
        total_row_count=len(labeled_frame),
        fraud_row_count=int(labeled_frame["Class"].sum()),
        duplicate_row_count=0,
    )
    training_provenance = training_provenance_metadata(
        producer_policy=SYNTHETIC_PRODUCER_POLICY,
        model_fit=model_fit,
        calibrator_fit=None,
        threshold_selection=None,
        evaluation=None,
        quarantine=None,
    )
    bundle = ModelBundle(
        preprocessor=preprocessor,
        model=model,
        calibrator=None,
        operating_threshold=0.53,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint=training_provenance.data_roles_sha256,
        model_version=SYNTHETIC_MODEL_VERSION,
        intended_use=intended_use_metadata(SYNTHETIC_PRODUCER_POLICY),
        threshold_provenance=threshold_provenance_metadata(
            producer_policy=SYNTHETIC_PRODUCER_POLICY,
            value=0.53,
            calibrated=False,
        ),
        training_provenance=training_provenance,
    )
    return bundle, request


def create_synthetic_bundle(output_dir: Path) -> Path:
    """Persist the bundle and deterministic smoke request/expected response."""
    bundle, request = build_synthetic_bundle()
    frame = pd.DataFrame([request], columns=ALL_FEATURES)
    raw_score = float(bundle.model.predict_proba(bundle.preprocessor.transform(frame))[0, 1])
    expected = {
        "decision": "review" if raw_score >= bundle.operating_threshold else "pass",
        "decision_score": raw_score,
        "model_version": bundle.model_version,
        "operating_threshold": bundle.operating_threshold,
        "raw_score": raw_score,
        "score_type": bundle.score_type,
    }
    manifest = save_model_bundle(
        bundle,
        output_dir,
        additional_files={
            "smoke_request.json": (
                json.dumps(request, indent=2, sort_keys=True, allow_nan=False) + "\n"
            ).encode("utf-8"),
            "smoke_expected.json": (
                json.dumps(expected, indent=2, sort_keys=True, allow_nan=False) + "\n"
            ).encode("utf-8"),
        },
    )
    return manifest


def directory_fingerprint(output_dir: Path) -> str:
    """Hash names and bytes for reproducibility diagnostics."""
    digest = hashlib.sha256()
    for path in sorted(item for item in output_dir.iterdir() if item.is_file()):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a synthetic-only SecureSwipe API smoke-test bundle."
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.expanduser().resolve()
    manifest = create_synthetic_bundle(output)
    print(
        json.dumps(
            {
                "artifact_kind": "synthetic_smoke_only",
                "directory_sha256": directory_fingerprint(output),
                "manifest": str(manifest),
                "model_version": SYNTHETIC_MODEL_VERSION,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
