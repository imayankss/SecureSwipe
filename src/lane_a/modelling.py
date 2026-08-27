"""Lane A modelling: preprocessing and the four predeclared model families.

Everything here is fitted on the ``training`` role only. The four families are
fixed in advance and no search of any kind is performed: no hyperparameter
search, no feature search, no seed search, no model-family search. Parameters
are resource-bounded constants chosen to run serially on a laptop, and they are
recorded verbatim in the run manifest.

This module does not import Lane B's feature contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.lane_a.serving_schema import (
    CATEGORICAL_FIELDS,
    IDENTITY_PRESENCE_FEATURE,
    NUMERIC_FIELDS,
    SCHEMA_FIELD_NAMES,
)

RANDOM_SEED = 42
#: Rare categories are folded into one bucket so the encoded width stays bounded
#: and unseen categories at scoring time have somewhere well-defined to go.
MIN_CATEGORY_FREQUENCY = 100
MODEL_ORDER: tuple[str, ...] = (
    "dummy_majority",
    "logistic_regression",
    "random_forest",
    "xgboost",
)


class ModellingError(RuntimeError):
    """Raised when a model cannot be built or trained within the declared bounds."""


@dataclass
class TrainedModel:
    """One fitted pipeline plus the facts needed to report it honestly."""

    name: str
    pipeline: Pipeline
    parameters: Mapping[str, Any]
    fit_seconds: float
    failed: bool = False
    failure_reason: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def build_preprocessor() -> ColumnTransformer:
    """Preprocessing fitted on training only; identical for all four models.

    Numeric columns are median-imputed with an explicit missing indicator, so
    missingness survives as signal rather than being erased by the fill. The
    reserved missing token is simply another category, so categorical
    missingness also survives.
    """
    numeric = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    categorical = OneHotEncoder(
        handle_unknown="infrequent_if_exist",
        min_frequency=MIN_CATEGORY_FREQUENCY,
        sparse_output=False,
        dtype=np.float32,
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric, list(NUMERIC_FIELDS)),
            ("categorical", categorical, list(CATEGORICAL_FIELDS)),
            ("boolean", "passthrough", [IDENTITY_PRESENCE_FEATURE]),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def class_weight_from_training(y_train: np.ndarray) -> float:
    """Positive-class weight computed from training labels only."""
    positives = int(np.sum(y_train == 1))
    negatives = int(np.sum(y_train == 0))
    if positives == 0:
        raise ModellingError("Training labels contain no positive class.")
    return negatives / positives


def model_specifications(scale_pos_weight: float) -> dict[str, dict[str, Any]]:
    """Fixed, resource-bounded parameters. No search is performed over these."""
    return {
        "dummy_majority": {
            "strategy": "most_frequent",
        },
        "logistic_regression": {
            "solver": "lbfgs",
            "max_iter": 1000,
            "class_weight": "balanced",
            "random_state": RANDOM_SEED,
            "n_jobs": None,
        },
        "random_forest": {
            "n_estimators": 100,
            "max_depth": 12,
            "min_samples_leaf": 25,
            "class_weight": "balanced_subsample",
            "random_state": RANDOM_SEED,
            "n_jobs": 4,
        },
        "xgboost": {
            "n_estimators": 300,
            "max_depth": 6,
            "learning_rate": 0.1,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "tree_method": "hist",
            "eval_metric": "aucpr",
            "objective": "binary:logistic",
            "scale_pos_weight": scale_pos_weight,
            "random_state": RANDOM_SEED,
            "n_jobs": 4,
        },
    }


def _estimator(name: str, parameters: Mapping[str, Any]) -> Any:
    if name == "dummy_majority":
        return DummyClassifier(**parameters)
    if name == "logistic_regression":
        return LogisticRegression(**parameters)
    if name == "random_forest":
        return RandomForestClassifier(**parameters)
    if name == "xgboost":
        from xgboost import XGBClassifier

        return XGBClassifier(**parameters)
    raise ModellingError(f"Unknown model {name!r}.")


def build_pipeline(name: str, parameters: Mapping[str, Any]) -> Pipeline:
    """Preprocessing plus estimator. One object, so nothing can be fitted twice."""
    return Pipeline(
        steps=[("preprocess", build_preprocessor()), ("model", _estimator(name, parameters))]
    )


def positive_scores(pipeline: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    """Positive-class scores in [0, 1]. Raises rather than guessing."""
    if not hasattr(pipeline, "predict_proba"):
        raise ModellingError("Pipeline exposes no predict_proba.")
    proba = pipeline.predict_proba(frame[list(SCHEMA_FIELD_NAMES)])
    if proba.ndim != 2 or proba.shape[1] != 2:
        raise ModellingError("Expected two-column probability output.")
    return np.asarray(proba[:, 1], dtype=float)


def build_variant_preprocessor(
    numeric: tuple[str, ...], categorical: tuple[str, ...], boolean: tuple[str, ...]
) -> ColumnTransformer:
    """v2 variant-aware preprocessor. Same transformations as the v1 baseline.

    Only the column lists differ between variants; the transformation
    definitions are identical, so a variant comparison isolates feature-set
    value rather than preprocessing changes.
    """
    numeric_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    categorical_encoder = OneHotEncoder(
        handle_unknown="infrequent_if_exist",
        min_frequency=MIN_CATEGORY_FREQUENCY,
        sparse_output=False,
        dtype=np.float32,
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, list(numeric)),
            ("categorical", categorical_encoder, list(categorical)),
            ("boolean", "passthrough", list(boolean)),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
