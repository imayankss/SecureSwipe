"""Canonical in-process scoring shared by serving and offline monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.artifacts.bundle import ModelBundle, positive_class_index
from src.preprocessing.preprocessors import validate_features_for_preprocessing


class ScoreIntegrityError(RuntimeError):
    """Raised when a fitted bundle returns malformed numerical output."""


@dataclass(frozen=True)
class BundleScores:
    raw_scores: np.ndarray
    calibrated_probabilities: np.ndarray | None
    decision_scores: np.ndarray


def _positive_scores(model: Any, features: object) -> np.ndarray:
    probabilities = np.asarray(model.predict_proba(features), dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 2:
        raise ScoreIntegrityError("Model predict_proba output must have two columns.")
    scores = probabilities[:, positive_class_index(model)]
    if not np.isfinite(scores).all() or np.logical_or(scores < 0.0, scores > 1.0).any():
        raise ScoreIntegrityError("Model produced an invalid raw score.")
    return scores


def _calibrate(calibrator: Any, raw_scores: np.ndarray) -> np.ndarray:
    inputs = raw_scores.reshape(-1, 1)
    if hasattr(calibrator, "predict_proba"):
        output = np.asarray(calibrator.predict_proba(inputs), dtype=float)
        if output.ndim != 2 or output.shape[1] != 2:
            raise ScoreIntegrityError("Calibrator predict_proba output must have two columns.")
        calibrated = output[:, positive_class_index(calibrator, component="calibrator")]
    else:
        calibrated = np.asarray(calibrator.predict(inputs), dtype=float).ravel()
    if calibrated.shape != raw_scores.shape or not np.isfinite(calibrated).all():
        raise ScoreIntegrityError("Calibrator produced malformed output.")
    if np.logical_or(calibrated < 0.0, calibrated > 1.0).any():
        raise ScoreIntegrityError("Calibrator output must be in [0, 1].")
    return calibrated


def score_bundle_frame(bundle: ModelBundle, frame: pd.DataFrame) -> BundleScores:
    """Score one canonical raw-feature frame without changing its row order."""
    bundle.validate()
    if frame.empty:
        raise ValueError("At least one transaction is required.")
    validate_features_for_preprocessing(frame, expected_features=list(bundle.feature_schema))
    transformed = bundle.preprocessor.transform(frame)
    raw_scores = _positive_scores(bundle.model, transformed)
    if len(raw_scores) != len(frame):
        raise ScoreIntegrityError("Model score count does not match the input row count.")
    calibrated = (
        _calibrate(bundle.calibrator, raw_scores) if bundle.calibrator is not None else None
    )
    decision_scores = calibrated if calibrated is not None else raw_scores
    return BundleScores(raw_scores, calibrated, decision_scores)
