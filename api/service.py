"""Thread-safe, bundle-backed prediction service."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from api.schemas import PredictionResult, ScoreType, TransactionFeatures
from src.artifacts.bundle import BUNDLE_FORMAT_VERSION, ModelBundle
from src.inference.risk_scoring import threshold_decision
from src.preprocessing.preprocessors import validate_features_for_preprocessing


class ModelUnavailableError(RuntimeError):
    """Raised when inference is requested without a verified bundle."""


class PredictionIntegrityError(RuntimeError):
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

    @staticmethod
    def _positive_scores(model: Any, features: object) -> np.ndarray:
        probabilities = np.asarray(model.predict_proba(features), dtype=float)
        if probabilities.ndim != 2 or probabilities.shape[1] != 2:
            raise PredictionIntegrityError("Model predict_proba output must have two columns.")
        scores = probabilities[:, 1]
        if not np.isfinite(scores).all() or np.logical_or(scores < 0.0, scores > 1.0).any():
            raise PredictionIntegrityError("Model produced an invalid raw score.")
        return scores

    @staticmethod
    def _calibrate(calibrator: Any, raw_scores: np.ndarray) -> np.ndarray:
        inputs = raw_scores.reshape(-1, 1)
        if hasattr(calibrator, "predict_proba"):
            output = np.asarray(calibrator.predict_proba(inputs), dtype=float)
            calibrated = (
                output[:, 1] if output.ndim == 2 and output.shape[1] == 2 else output.ravel()
            )
        else:
            calibrated = np.asarray(calibrator.predict(inputs), dtype=float).ravel()
        if calibrated.shape != raw_scores.shape or not np.isfinite(calibrated).all():
            raise PredictionIntegrityError("Calibrator produced malformed output.")
        if np.logical_or(calibrated < 0.0, calibrated > 1.0).any():
            raise PredictionIntegrityError("Calibrator output must be in [0, 1].")
        return calibrated

    def predict_many(self, transactions: Iterable[TransactionFeatures]) -> list[PredictionResult]:
        bundle = self.require_bundle()
        rows = [transaction.canonical_values() for transaction in transactions]
        if not rows:
            raise ValueError("At least one transaction is required.")
        frame = pd.DataFrame(rows, columns=bundle.feature_schema)
        validate_features_for_preprocessing(frame, expected_features=list(bundle.feature_schema))

        with self._prediction_lock:
            transformed = bundle.preprocessor.transform(frame)
            raw_scores = self._positive_scores(bundle.model, transformed)
            calibrated = (
                self._calibrate(bundle.calibrator, raw_scores)
                if bundle.calibrator is not None
                else None
            )

        decision_scores = calibrated if calibrated is not None else raw_scores
        results: list[PredictionResult] = []
        for index, raw_score in enumerate(raw_scores):
            calibrated_probability = float(calibrated[index]) if calibrated is not None else None
            decision_score = float(decision_scores[index])
            if not math.isfinite(decision_score):
                raise PredictionIntegrityError("Decision score is not finite.")
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
