"""Forward blocked development evaluation tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from src.evaluation.temporal_validation import (
    evaluate_blocked_development,
    make_expanding_time_folds,
)
from src.preprocessing.feature_config import ALL_FEATURES


def _development_fixture(rows: int = 80) -> tuple[pd.DataFrame, np.ndarray]:
    index = np.arange(rows, dtype=float)
    values: dict[str, np.ndarray] = {
        "Time": index,
        "Amount": 1.0 + index,
    }
    for feature_index in range(1, 29):
        values[f"V{feature_index}"] = np.cos(index / (feature_index + 2)) + feature_index
    features = pd.DataFrame(values, columns=ALL_FEATURES)
    labels = (index.astype(int) % 4 == 0).astype(int)
    return features, labels


def test_time_folds_are_forward_disjoint_and_keep_ties_together() -> None:
    times = np.repeat(np.arange(8, dtype=float), 2)
    folds = make_expanding_time_folds(times, n_splits=3)
    assert len(folds) == 3
    for fold in folds:
        assert set(fold.train_indices).isdisjoint(set(fold.validation_indices))
        assert times[fold.train_indices].max() < times[fold.validation_indices].min()
        assert not set(times[fold.train_indices]).intersection(times[fold.validation_indices])


@pytest.mark.parametrize("invalid", [[0.0, float("nan")], [0.0, -1.0]])
def test_time_folds_reject_invalid_time_values(invalid: list[float]) -> None:
    with pytest.raises(ValueError):
        make_expanding_time_folds(invalid)


def test_blocked_evaluation_fits_forward_and_is_deterministic() -> None:
    features, labels = _development_fixture()

    def factory() -> LogisticRegression:
        return LogisticRegression(random_state=42, max_iter=1_000)

    first = evaluate_blocked_development(features, labels, factory, n_splits=3)
    second = evaluate_blocked_development(features, labels, factory, n_splits=3)

    assert first.evaluation_scope == "development_blocked"
    assert first.data_fingerprint == second.data_fingerprint
    pd.testing.assert_frame_equal(first.fold_metrics, second.fold_metrics)
    pd.testing.assert_frame_equal(first.predictions, second.predictions)
    assert set(first.predictions["evaluation_scope"]) == {"development_blocked"}
    assert len(first.fold_metrics) == 3
    assert np.logical_and(
        first.predictions["raw_score"] >= 0.0,
        first.predictions["raw_score"] <= 1.0,
    ).all()
    assert (first.fold_metrics["train_time_max"] < first.fold_metrics["validation_time_min"]).all()


def test_blocked_evaluation_rejects_duplicate_development_rows() -> None:
    features, labels = _development_fixture()
    features.iloc[1] = features.iloc[0]
    labels[1] = labels[0]
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_blocked_development(
            features,
            labels,
            lambda: LogisticRegression(random_state=42),
            n_splits=3,
        )
