"""Synthetic serving bundle for tests that need a ready ModelService.

`artifacts/` is generated output and is **git-ignored**, so it does not exist on
a clean checkout or in CI. Tests must therefore never load a bundle from it.

This builds an equivalent in-process bundle from synthetic data, following the
approved `synthetic_api_smoke_v1` producer policy the API smoke tests use. Trusted-path validation in
`src.artifacts.bundle` is untouched: nothing here writes a fake artifact to disk
or relaxes a check.

The bundle carries a synthetic `model_artifact_sha256` because the audit writer
refuses to start without a verified fingerprint.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from src.artifacts.bundle import (
    ModelBundle,
    data_role_metadata,
    intended_use_metadata,
    threshold_provenance_metadata,
    training_provenance_metadata,
)
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor

#: Synthetic, obviously non-production fingerprint.
SYNTHETIC_MODEL_ARTIFACT_SHA256 = "a" * 64
SYNTHETIC_TRAINING_FINGERPRINT = "b" * 64
SYNTHETIC_OPERATING_THRESHOLD = 0.53

#: Required by the approved `synthetic_api_smoke_v1` producer policy.
SYNTHETIC_MODEL_VERSION = "synthetic-smoke-1"


def _training_provenance(fingerprint: str = SYNTHETIC_TRAINING_FINGERPRINT):
    return training_provenance_metadata(
        producer_policy="synthetic_api_smoke_v1",
        model_fit=data_role_metadata(
            fingerprint_sha256=fingerprint,
            total_row_count=80,
            fraud_row_count=40,
            duplicate_row_count=0,
        ),
        calibrator_fit=None,
        threshold_selection=None,
        evaluation=None,
        quarantine=None,
    )


def build_synthetic_serving_bundle(seed: int = 42) -> ModelBundle:
    """Deterministic synthetic bundle over the published feature contract.

    Uses the same 30-field schema the serving contract expects, so synthetic
    request payloads exercise the real request path unchanged.
    """
    rng = np.random.default_rng(seed)
    training = pd.DataFrame(
        rng.normal(size=(80, len(ALL_FEATURES))),
        columns=list(ALL_FEATURES),
    )
    training["Time"] = np.arange(80, dtype=float)
    training["Amount"] = np.abs(training["Amount"] * 100.0)
    labels = np.array([0, 1] * 40)

    preprocessor = fit_preprocessor(training, build_preprocessor())
    preprocessor.set_output(transform="pandas")
    model = LogisticRegression(random_state=seed).fit(
        preprocessor.transform(training), labels
    )
    provenance = _training_provenance()

    return ModelBundle(
        preprocessor=preprocessor,
        model=model,
        calibrator=None,
        operating_threshold=SYNTHETIC_OPERATING_THRESHOLD,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint=provenance.data_roles_sha256,
        model_version=SYNTHETIC_MODEL_VERSION,
        intended_use=intended_use_metadata("synthetic_api_smoke_v1"),
        threshold_provenance=threshold_provenance_metadata(
            producer_policy="synthetic_api_smoke_v1",
            value=SYNTHETIC_OPERATING_THRESHOLD,
            calibrated=False,
        ),
        training_provenance=provenance,
        model_artifact_sha256=SYNTHETIC_MODEL_ARTIFACT_SHA256,
    )
