"""Thread-safe, bundle-backed prediction service."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from api.schemas import PredictionResult, ScoreType, TransactionFeatures
from src.artifacts.bundle import BUNDLE_FORMAT_VERSION, ModelBundle
from src.inference.batch_scoring import ScoreIntegrityError, score_bundle_frame
from src.inference.risk_scoring import threshold_decision


class ModelUnavailableError(RuntimeError):
    """Raised when inference is requested without a verified bundle."""


class PredictionIntegrityError(ScoreIntegrityError):
    """Raised when a verified model returns malformed numerical output."""


@dataclass(frozen=True)
class ModelInfo:
    model_version: str
    bundle_format_version: str
    score_type: ScoreType
    calibrated: bool
    operating_threshold: float
    feature_schema: tuple[str, ...]
    training_data_fingerprint: str


class ModelService:
    """Own one immutable verified bundle and serialize estimator access."""

    def __init__(self, bundle: ModelBundle | None = None) -> None:
        if bundle is not None:
            bundle.validate()
        self._bundle = bundle
        self._prediction_lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._bundle is not None

    @property
    def model_version(self) -> str | None:
        return self._bundle.model_version if self._bundle else None

    def require_bundle(self) -> ModelBundle:
        if self._bundle is None:
            raise ModelUnavailableError(
                "No verified model bundle is configured; inference is unavailable."
            )
        return self._bundle

    def model_info(self) -> ModelInfo:
        bundle = self.require_bundle()
        return ModelInfo(
            model_version=bundle.model_version,
            bundle_format_version=BUNDLE_FORMAT_VERSION,
            score_type=bundle.score_type,
            calibrated=bundle.calibrator is not None,
            operating_threshold=bundle.operating_threshold,
            feature_schema=bundle.feature_schema,
            training_data_fingerprint=bundle.training_data_fingerprint,
        )

    def predict_many(self, transactions: Iterable[TransactionFeatures]) -> list[PredictionResult]:
        bundle = self.require_bundle()
        rows = [transaction.canonical_values() for transaction in transactions]
        if not rows:
            raise ValueError("At least one transaction is required.")
        frame = pd.DataFrame(rows, columns=bundle.feature_schema)
        with self._prediction_lock:
            try:
                scored = score_bundle_frame(bundle, frame)
            except ScoreIntegrityError as exc:
                raise PredictionIntegrityError(str(exc)) from exc

        results: list[PredictionResult] = []
        for index, raw_score in enumerate(scored.raw_scores):
            calibrated_probability = (
                float(scored.calibrated_probabilities[index])
                if scored.calibrated_probabilities is not None
                else None
            )
            decision_score = float(scored.decision_scores[index])
            results.append(
                PredictionResult(
                    raw_score=float(raw_score),
                    calibrated_probability=calibrated_probability,
                    decision_score=decision_score,
                    score_type=bundle.score_type,
                    operating_threshold=bundle.operating_threshold,
                    decision=threshold_decision(decision_score, bundle.operating_threshold),
                    model_version=bundle.model_version,
                )
            )
        return results

    def predict_one(self, transaction: TransactionFeatures) -> PredictionResult:
        return self.predict_many([transaction])[0]
