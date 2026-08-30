"""Versioned, strict request and response contracts for SecureSwipe's API."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from src.artifacts.bundle import EvidenceCategory
from src.preprocessing.feature_config import ALL_FEATURES

API_SCHEMA_VERSION: Literal["1.0"] = "1.0"
ScoreType = Literal["raw_score", "calibrated_probability"]
MAX_BATCH_SIZE = 100

PcaValue = Annotated[FiniteFloat, Field(ge=-1_000_000.0, le=1_000_000.0)]
TimeValue = Annotated[FiniteFloat, Field(ge=0.0, le=1_000_000_000.0)]
AmountValue = Annotated[FiniteFloat, Field(ge=0.0, le=1_000_000_000.0)]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TransactionFeatures(StrictContract):
    """Named raw features; JSON object order is normalized canonically."""

    Time: TimeValue
    V1: PcaValue
    V2: PcaValue
    V3: PcaValue
    V4: PcaValue
    V5: PcaValue
    V6: PcaValue
    V7: PcaValue
    V8: PcaValue
    V9: PcaValue
    V10: PcaValue
    V11: PcaValue
    V12: PcaValue
    V13: PcaValue
    V14: PcaValue
    V15: PcaValue
    V16: PcaValue
    V17: PcaValue
    V18: PcaValue
    V19: PcaValue
    V20: PcaValue
    V21: PcaValue
    V22: PcaValue
    V23: PcaValue
    V24: PcaValue
    V25: PcaValue
    V26: PcaValue
    V27: PcaValue
    V28: PcaValue
    Amount: AmountValue

    def canonical_values(self) -> dict[str, float]:
        data = self.model_dump()
        return {feature: float(data[feature]) for feature in ALL_FEATURES}


if list(TransactionFeatures.model_fields) != list(ALL_FEATURES):
    raise RuntimeError("API feature schema does not match the canonical model schema.")


class BatchPredictionRequest(StrictContract):
    transactions: Annotated[
        list[TransactionFeatures],
        Field(min_length=1, max_length=MAX_BATCH_SIZE),
    ]


class PredictionProvenance(StrictContract):
    training_data_fingerprint: str
    evidence_category: EvidenceCategory
    historical_taint: bool
    decision_eligible: bool
    historical_metrics_claimed: bool
    evaluation_performed: bool


class PredictionResult(StrictContract):
    raw_score: float
    calibrated_probability: float | None
    decision_score: float
    score_type: ScoreType
    operating_threshold: float
    decision: Literal["human_review", "below_review_threshold"]
    model_version: str
    bundle_format_version: str
    provenance: PredictionProvenance


class PredictionResponse(PredictionResult):
    schema_version: Literal["1.0"] = API_SCHEMA_VERSION
    request_id: str


class BatchPredictionResponse(StrictContract):
    schema_version: Literal["1.0"] = API_SCHEMA_VERSION
    request_id: str
    model_version: str
    count: int
    predictions: list[PredictionResult]


class HealthResponse(StrictContract):
    schema_version: Literal["1.0"] = API_SCHEMA_VERSION
    status: Literal["live", "ready", "not_ready"]
    model_version: str | None = None


class ModelInfoResponse(StrictContract):
    schema_version: Literal["1.0"] = API_SCHEMA_VERSION
    model_version: str
    bundle_format_version: str
    score_type: ScoreType
    calibrated: bool
    operating_threshold: float
    feature_schema: list[str]
    model_artifact_sha256: str | None
    training_data_fingerprint: str
    evidence_category: EvidenceCategory
    historical_taint: bool
    decision_eligible: bool
    historical_metrics_claimed: bool
    evaluation_performed: bool


class ErrorDetail(StrictContract):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(StrictContract):
    schema_version: Literal["1.0"] = API_SCHEMA_VERSION
    request_id: str
    error: ErrorDetail
