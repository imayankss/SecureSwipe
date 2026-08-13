"""Forward blocked evaluation restricted to development data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from src.data.data_loader import fingerprint_dataframe, validate_dataset_schema
from src.preprocessing.feature_config import ALL_FEATURES
from src.preprocessing.preprocessors import build_preprocessor, fit_preprocessor


@dataclass(frozen=True)
class BlockedFold:
    fold: int
    train_indices: np.ndarray
    validation_indices: np.ndarray
    train_time_max: float
    validation_time_min: float
    validation_time_max: float


@dataclass(frozen=True)
class BlockedEvaluation:
    evaluation_scope: str
    data_fingerprint: str
    fold_metrics: pd.DataFrame
    predictions: pd.DataFrame


def make_expanding_time_folds(
    times: Sequence[float] | np.ndarray,
    *,
    n_splits: int = 3,
    gap: float = 0.0,
) -> list[BlockedFold]:
    """Create expanding-train, forward-validation folds without splitting time ties."""
    try:
        values = np.asarray(times, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("times must be numeric.") from exc
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("times must be a non-empty finite one-dimensional array.")
    if (values < 0.0).any():
        raise ValueError("times must be non-negative.")
    if not isinstance(n_splits, int) or n_splits < 1:
        raise ValueError("n_splits must be an integer >= 1.")
    if not np.isfinite(gap) or gap < 0.0:
        raise ValueError("gap must be finite and non-negative.")

    unique_times = np.unique(values)
    if len(unique_times) < n_splits + 1:
        raise ValueError("Not enough unique timestamps for the requested folds.")
    time_blocks = np.array_split(unique_times, n_splits + 1)
    folds: list[BlockedFold] = []
    for fold_index in range(n_splits):
        validation_times = time_blocks[fold_index + 1]
        validation_min = float(validation_times[0])
        train_cutoff = validation_min - gap
        train_indices = np.flatnonzero(values < train_cutoff)
        validation_indices = np.flatnonzero(np.isin(values, validation_times))
        if train_indices.size == 0 or validation_indices.size == 0:
            raise ValueError("gap or fold configuration produced an empty partition.")
        train_max = float(values[train_indices].max())
        if not train_max + gap <= validation_min:
            raise RuntimeError("Temporal fold boundary invariant failed.")
        folds.append(
            BlockedFold(
                fold=fold_index,
                train_indices=train_indices,
                validation_indices=validation_indices,
                train_time_max=train_max,
                validation_time_min=validation_min,
                validation_time_max=float(validation_times[-1]),
            )
        )
    return folds


def _positive_scores(model: object, features: object) -> np.ndarray:
    if not hasattr(model, "predict_proba"):
        raise ValueError("Blocked evaluation requires predict_proba for bounded raw scores.")
    probabilities = np.asarray(model.predict_proba(features), dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 2:
        raise ValueError("predict_proba must return two columns.")
    scores = probabilities[:, 1]
    if not np.isfinite(scores).all() or np.logical_or(scores < 0.0, scores > 1.0).any():
        raise ValueError("Model returned invalid bounded scores.")
    return scores


def evaluate_blocked_development(
    features: pd.DataFrame,
    labels: Sequence[int] | np.ndarray,
    estimator_factory: Callable[[], Any],
    *,
    n_splits: int = 3,
    gap: float = 0.0,
) -> BlockedEvaluation:
    """Fit preprocessing/model inside each forward fold and return OOF evidence.

    Callers must pass training/development rows only. The observed historical
    test partition is intentionally outside this function's contract.
    """
    if list(features.columns) != list(ALL_FEATURES):
        raise ValueError("features must match the canonical ordered raw feature schema.")
    label_values = np.asarray(labels)
    if label_values.ndim != 1 or len(label_values) != len(features):
        raise ValueError("labels must be one-dimensional and match feature rows.")
    labeled = features.copy()
    labeled["Class"] = label_values
    validate_dataset_schema(labeled)
    fingerprint = fingerprint_dataframe(labeled)
    folds = make_expanding_time_folds(features["Time"].to_numpy(), n_splits=n_splits, gap=gap)

    metric_rows: list[dict[str, float | int | str]] = []
    prediction_frames: list[pd.DataFrame] = []
    for fold in folds:
        train_labels = label_values[fold.train_indices].astype(int)
        validation_labels = label_values[fold.validation_indices].astype(int)
        if set(np.unique(train_labels)) != {0, 1} or set(np.unique(validation_labels)) != {
            0,
            1,
        }:
            raise ValueError(f"Fold {fold.fold} must contain both classes in each partition.")
        train_features = features.iloc[fold.train_indices]
        validation_features = features.iloc[fold.validation_indices]
        preprocessor = fit_preprocessor(train_features, build_preprocessor())
        model = estimator_factory()
        model.fit(preprocessor.transform(train_features), train_labels)
        scores = _positive_scores(model, preprocessor.transform(validation_features))

        metric_rows.append(
            {
                "average_precision": float(average_precision_score(validation_labels, scores)),
                "brier_score": float(brier_score_loss(validation_labels, scores)),
                "fold": fold.fold,
                "roc_auc": float(roc_auc_score(validation_labels, scores)),
                "train_rows": len(fold.train_indices),
                "train_time_max": fold.train_time_max,
                "validation_fraud": int(validation_labels.sum()),
                "validation_rows": len(fold.validation_indices),
                "validation_time_max": fold.validation_time_max,
                "validation_time_min": fold.validation_time_min,
            }
        )
        prediction_frames.append(
            pd.DataFrame(
                {
                    "evaluation_scope": "development_blocked",
                    "fold": fold.fold,
                    "original_index": fold.validation_indices,
                    "raw_score": scores,
                    "Time": validation_features["Time"].to_numpy(dtype=float),
                    "y_true": validation_labels,
                }
            )
        )

    return BlockedEvaluation(
        evaluation_scope="development_blocked",
        data_fingerprint=fingerprint,
        fold_metrics=pd.DataFrame(metric_rows),
        predictions=pd.concat(prediction_frames, ignore_index=True),
    )
