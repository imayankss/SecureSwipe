"""Internal score-free V2 representation for future PostgreSQL replay."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas import PredictionResult
from api.service import ModelService
from src.artifacts.bundle import BUNDLE_FORMAT_VERSION, EvidenceCategory

V2_SCHEMA_VERSION: Literal["2.0"] = "2.0"
V2_RESPONSE_PROFILE: Literal["postgres-scale-bounded-v1"] = (
    "postgres-scale-bounded-v1"
)


class BoundedResponseIntegrityError(RuntimeError):
    """Raised when runtime output cannot be bound to the loaded bundle metadata."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, populate_by_name=True, serialize_by_alias=True
    )


class BoundedModelProvenance(_StrictModel):
    model_version: str
    bundle_format_version: str
    model_artifact_sha256: str
    training_data_fingerprint: str
    evidence_category: EvidenceCategory
    historical_taint: bool
    decision_eligible: bool
    historical_metrics_claimed: bool
    evaluation_performed: bool


class BoundedPolicyProvenance(_StrictModel):
    producer_policy: str
    producer_policy_sha256: str
    operating_threshold: float
    threshold_source: str
    threshold_model_linkage: str
    threshold_purpose: str
    threshold_calibrated: bool
    threshold_cost_optimal: bool
    threshold_razorpay_approved: bool
    threshold_production_approved: bool


class BoundedSchemaProvenance(_StrictModel):
    api_schema_version: Literal["2.0"] = V2_SCHEMA_VERSION
    feature_schema_sha256: str


class BoundedPredictionRepresentation(_StrictModel):
    """Allowlisted durable body; the caller's plaintext request ID is never included."""

    schema_version: Literal["2.0"] = V2_SCHEMA_VERSION
    response_profile: Literal["postgres-scale-bounded-v1"] = V2_RESPONSE_PROFILE
    status: Literal["completed"] = "completed"
    decision: Literal["human_review", "below_review_threshold"]
    model: BoundedModelProvenance
    policy: BoundedPolicyProvenance
    schema_provenance: BoundedSchemaProvenance = Field(alias="schema")


def canonical_response_bytes(response: BoundedPredictionRepresentation) -> bytes:
    return json.dumps(
        response.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def response_sha256(response: BoundedPredictionRepresentation) -> str:
    return hashlib.sha256(canonical_response_bytes(response)).hexdigest()


def build_bounded_prediction_response(
    *, service: ModelService, result: PredictionResult
) -> BoundedPredictionRepresentation:
    """Build V2 metadata exclusively from the verified bundle loaded by the service."""
    bundle = service.require_bundle()
    bundle.validate()
    fingerprint = bundle.model_artifact_sha256
    if fingerprint is None:
        raise BoundedResponseIntegrityError(
            "A verified model-artifact fingerprint is required for bounded replay."
        )
    expected_provenance = {
        "training_data_fingerprint": bundle.training_data_fingerprint,
        **bundle.intended_use.to_dict(),
    }
    actual_provenance = result.provenance.model_dump(mode="json")
    expected_result_provenance = {
        key: value
        for key, value in expected_provenance.items()
        if key
        in {
            "training_data_fingerprint",
            "evidence_category",
            "historical_taint",
            "decision_eligible",
            "historical_metrics_claimed",
            "evaluation_performed",
        }
    }
    if (
        result.model_version != bundle.model_version
        or result.bundle_format_version != BUNDLE_FORMAT_VERSION
        or result.operating_threshold != bundle.operating_threshold
        or actual_provenance != expected_result_provenance
    ):
        raise BoundedResponseIntegrityError(
            "Prediction provenance does not match the loaded bundle."
        )

    threshold = bundle.threshold_provenance
    schema_digest = hashlib.sha256(
        json.dumps(
            list(bundle.feature_schema), sort_keys=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return BoundedPredictionRepresentation(
        decision=result.decision,
        model=BoundedModelProvenance(
            model_version=bundle.model_version,
            bundle_format_version=BUNDLE_FORMAT_VERSION,
            model_artifact_sha256=fingerprint,
            training_data_fingerprint=bundle.training_data_fingerprint,
            evidence_category=bundle.intended_use.evidence_category,
            historical_taint=bundle.intended_use.historical_taint,
            decision_eligible=bundle.intended_use.decision_eligible,
            historical_metrics_claimed=bundle.intended_use.historical_metrics_claimed,
            evaluation_performed=bundle.intended_use.evaluation_performed,
        ),
        policy=BoundedPolicyProvenance(
            producer_policy=bundle.intended_use.producer_policy,
            producer_policy_sha256=bundle.intended_use.producer_policy_sha256,
            operating_threshold=float(bundle.operating_threshold),
            threshold_source=threshold.source,
            threshold_model_linkage=threshold.model_linkage,
            threshold_purpose=threshold.purpose,
            threshold_calibrated=threshold.calibrated,
            threshold_cost_optimal=threshold.cost_optimal,
            threshold_razorpay_approved=threshold.razorpay_approved,
            threshold_production_approved=threshold.production_approved,
        ),
        schema=BoundedSchemaProvenance(feature_schema_sha256=schema_digest),
    )
