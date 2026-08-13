"""
src/models/advanced_models.py
-------------------------------
Credit Card Fraud Detection & Risk Scoring System — Day 5

Advanced model utilities — XGBoost.

Responsibilities
----------------
* Compute ``scale_pos_weight`` from training labels only.
* Build, configure, and train an XGBoost classifier.
* Persist model artifacts with ``joblib``.
* Load previously saved artifacts.
* Expose feature importances as a ranked ``pandas.Series``.

Strict Day 5 scope — this module does NOT:
  - Access the validation or test sets.
  - Perform threshold tuning.
  - Generate PR / ROC curve plots.
  - Implement SHAP analysis.
  - Implement LightGBM (separate concern, Day 5 optional).

Upstream contract
-----------------
Processed training data is produced by Day 3:
  ``data/processed/X_train_processed.parquet``
  ``data/processed/y_train.parquet``

These files are loaded by ``scripts/run_day5_advanced_models.py``.
This module only receives already-loaded DataFrames and Series.

Dependency note
---------------
``xgboost`` is an optional project dependency.  A clear :class:`ImportError`
is raised at function-call time (not at import time) so the rest of the
project continues to work even if XGBoost is not installed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.artifacts.bundle import load_verified_joblib, write_checksum_sidecar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional xgboost import — deferred to call-site with a clear error
# ---------------------------------------------------------------------------

try:
    from xgboost import XGBClassifier

    _XGBOOST_AVAILABLE = True
except ImportError:  # pragma: no cover
    _XGBOOST_AVAILABLE = False
    XGBClassifier = None  # type: ignore[assignment,misc]


def _require_xgboost() -> None:
    """Raise a helpful :class:`ImportError` when xgboost is not installed."""
    if not _XGBOOST_AVAILABLE:
        raise ImportError(
            "xgboost is not installed.  Install it with:\n\n"
            "    pip install xgboost\n\n"
            "or add it to requirements.txt and re-run pip install."
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RANDOM_STATE: int = 42
DEFAULT_MODELS_DIR: Path = Path("artifacts/models")

# XGBoost hyper-parameters — centralised here so the runner script
# never has to hard-code them separately.
XGBOOST_PARAMS: dict[str, Any] = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "tree_method": "hist",
    "n_jobs": -1,
}

# Positive-class label (fraud).
_FRAUD_LABEL: int = 1
_LEGIT_LABEL: int = 0


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def validate_training_data(
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> None:
    """
    Validate that *X_train* and *y_train* are safe to use for model training.

    Parameters
    ----------
    X_train:
        Feature matrix.  Must be a non-empty :class:`~pandas.DataFrame` with
        only numeric columns and no missing values.  Must not contain the
        target column (``Class``).
    y_train:
        Binary target series.  Must contain only ``0`` and ``1``, have no
        missing values, and include at least one example of each class.

    Raises
    ------
    TypeError
        If *X_train* is not a :class:`~pandas.DataFrame` or *y_train* is not
        a :class:`~pandas.Series`.
    ValueError
        For any of the following conditions:

        * Either input is empty.
        * Row counts differ.
        * ``Class`` column is present in *X_train* (target leakage).
        * *y_train* contains values other than ``0`` and ``1``.
        * Only one class is present in *y_train*.
        * *X_train* has non-numeric columns.
        * *X_train* or *y_train* contains missing values.
    """
    if not isinstance(X_train, pd.DataFrame):
        raise TypeError(
            f"X_train must be a pandas DataFrame, got {type(X_train).__name__!r}."
        )
    if not isinstance(y_train, pd.Series):
        raise TypeError(
            f"y_train must be a pandas Series, got {type(y_train).__name__!r}."
        )

    if X_train.empty:
        raise ValueError("X_train is empty — cannot train a model on zero rows.")
    if y_train.empty:
        raise ValueError("y_train is empty — cannot train a model on zero rows.")

    if len(X_train) != len(y_train):
        raise ValueError(
            f"X_train has {len(X_train)} rows but y_train has {len(y_train)} rows.  "
            "They must have the same number of rows."
        )

    # Target leakage guard
    if "Class" in X_train.columns:
        raise ValueError(
            "Target column 'Class' was found in X_train.  "
            "Remove it before passing X_train to the model."
        )

    # Target validity
    unique_labels = set(y_train.dropna().unique())
    invalid_labels = unique_labels - {0, 1}
    if invalid_labels:
        raise ValueError(
            f"y_train contains unexpected values: {sorted(invalid_labels)}.  "
            "Only 0 (legitimate) and 1 (fraud) are allowed."
        )
    if y_train.isna().any():
        raise ValueError("y_train contains missing values.  Fill or drop them first.")
    if _FRAUD_LABEL not in unique_labels:
        raise ValueError(
            "y_train contains no fraud cases (Class=1).  "
            "Cannot train a meaningful fraud detector."
        )
    if _LEGIT_LABEL not in unique_labels:
        raise ValueError(
            "y_train contains only fraud cases (Class=1).  "
            "Both classes must be present."
        )

    # Feature matrix quality
    non_numeric = [c for c in X_train.columns if not pd.api.types.is_numeric_dtype(X_train[c])]
    if non_numeric:
        raise ValueError(
            f"X_train contains non-numeric columns: {non_numeric}.  "
            "All features must be numeric before training."
        )

    missing_counts = X_train.isna().sum()
    cols_with_missing = missing_counts[missing_counts > 0].index.tolist()
    if cols_with_missing:
        raise ValueError(
            f"X_train has missing values in columns: {cols_with_missing}.  "
            "Impute or drop them before training."
        )


# ---------------------------------------------------------------------------
# scale_pos_weight
# ---------------------------------------------------------------------------


def calculate_scale_pos_weight(y_train: pd.Series) -> float:
    """
    Compute the ``scale_pos_weight`` parameter for XGBoost from training
    labels only.

    XGBoost uses this value to up-weight the minority class (fraud) during
    training, compensating for severe class imbalance without altering the
    underlying data distribution.

    Formula
    -------
    .. code-block::

        scale_pos_weight = count(Class == 0) / count(Class == 1)

    This is the formula recommended in the official XGBoost documentation for
    imbalanced binary classification.

    Parameters
    ----------
    y_train:
        Binary training labels.  Must contain both ``0`` (legitimate) and
        ``1`` (fraud).

    Returns
    -------
    float
        The ratio of legitimate to fraudulent transactions in *y_train*.
        Always ≥ 1.0 for a fraud dataset (fraud is always the minority).

    Raises
    ------
    TypeError
        If *y_train* is not a :class:`~pandas.Series`.
    ValueError
        If *y_train* is empty, contains no fraud cases, or has missing values.

    Examples
    --------
    >>> import pandas as pd
    >>> y = pd.Series([0] * 990 + [1] * 10)
    >>> calculate_scale_pos_weight(y)
    99.0
    """
    if not isinstance(y_train, pd.Series):
        raise TypeError(
            f"y_train must be a pandas Series, got {type(y_train).__name__!r}."
        )
    if y_train.empty:
        raise ValueError("y_train is empty.  Cannot compute scale_pos_weight.")
    if y_train.isna().any():
        raise ValueError(
            "y_train contains missing values.  "
            "Fill or drop them before computing scale_pos_weight."
        )

    unique_labels = set(y_train.unique())
    invalid_labels = unique_labels - {_LEGIT_LABEL, _FRAUD_LABEL}
    if invalid_labels:
        raise ValueError(
            f"y_train must contain only 0 and 1, but found: {sorted(invalid_labels)}."
        )

    n_legit = int((y_train == _LEGIT_LABEL).sum())
    n_fraud = int((y_train == _FRAUD_LABEL).sum())

    if n_fraud == 0:
        raise ValueError(
            "y_train contains no positive fraud cases (Class=1).  "
            "scale_pos_weight cannot be computed without a positive class."
        )
    if n_legit == 0:
        raise ValueError(
            "y_train contains only fraud cases (Class=1) and no legitimate "
            "transactions.  Cannot compute a meaningful scale_pos_weight."
        )

    weight = n_legit / n_fraud

    logger.info(
        "scale_pos_weight = %d / %d = %.4f  "
        "(legitimate count / fraud count, training labels only)",
        n_legit,
        n_fraud,
        weight,
    )
    return weight


# ---------------------------------------------------------------------------
# Model construction
# ---------------------------------------------------------------------------


def build_xgboost_classifier(
    scale_pos_weight: float,
    random_state: int = RANDOM_STATE,
) -> "XGBClassifier":
    """
    Construct an *unfitted* XGBoost binary classifier with project defaults.

    The returned classifier is not yet trained.  Call
    :func:`train_xgboost_model` to fit it, or pass it directly to
    :func:`train_model`.

    Parameters
    ----------
    scale_pos_weight:
        Ratio of legitimate to fraudulent training samples.  Compute this
        with :func:`calculate_scale_pos_weight` **using y_train only** to
        avoid leakage.
    random_state:
        Seed for reproducibility.  Defaults to ``42`` (project-wide constant).

    Returns
    -------
    XGBClassifier
        Configured but unfitted classifier.

    Raises
    ------
    ImportError
        If the ``xgboost`` package is not installed.
    ValueError
        If *scale_pos_weight* is not a positive finite number.

    Notes
    -----
    Hyper-parameters are defined in :data:`XGBOOST_PARAMS` at the top of
    this module so they can be inspected and overridden in one place.

    XGBoost parameter guide (Day 5 baseline settings)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * ``n_estimators=300``       — number of boosting rounds; conservative
      enough not to overfit without early stopping.
    * ``max_depth=4``            — shallow trees reduce overfitting on
      tabular fraud data.
    * ``learning_rate=0.05``     — slow learning rate pairs well with 300
      estimators.
    * ``subsample=0.8``          — row subsampling adds regularisation.
    * ``colsample_bytree=0.8``   — feature subsampling per tree.
    * ``objective='binary:logistic'`` — outputs probabilities ∈ [0, 1].
    * ``eval_metric='aucpr'``    — optimises PR-AUC internally (aligns with
      project primary metric).
    * ``tree_method='hist'``     — fast histogram-based algorithm; works on
      CPU and GPU.
    * ``scale_pos_weight``       — compensates for fraud being the minority.
    """
    _require_xgboost()

    if not isinstance(scale_pos_weight, (int, float)) or np.isnan(scale_pos_weight):
        raise ValueError(
            f"scale_pos_weight must be a finite number, got {scale_pos_weight!r}."
        )
    if scale_pos_weight <= 0:
        raise ValueError(
            f"scale_pos_weight must be positive, got {scale_pos_weight}.  "
            "Use calculate_scale_pos_weight(y_train) to derive the correct value."
        )

    clf = XGBClassifier(
        **XGBOOST_PARAMS,
        scale_pos_weight=float(scale_pos_weight),
        random_state=random_state,
    )

    logger.info(
        "Built XGBClassifier  scale_pos_weight=%.4f  random_state=%d",
        scale_pos_weight,
        random_state,
    )
    return clf


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train_model(
    model: Any,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> Any:
    """
    Fit *model* on *X_train* and *y_train* after validating inputs.

    This is a thin, validated wrapper around ``model.fit()``.  It is
    intentionally generic so that :func:`train_xgboost_model` — and any
    future advanced model trainer — can share the same validation path.

    Parameters
    ----------
    model:
        An unfitted scikit-learn–compatible estimator (e.g.
        :class:`xgboost.XGBClassifier`).
    X_train:
        Pre-processed feature matrix from Day 3.  Must not include ``Class``.
    y_train:
        Binary target series.

    Returns
    -------
    object
        The same *model* object after fitting (in-place mutation, returned for
        convenience).

    Raises
    ------
    TypeError / ValueError
        Propagated from :func:`validate_training_data`.
    """
    validate_training_data(X_train, y_train)
    model.fit(X_train, y_train)
    logger.info(
        "Fitted %s on %d rows (%d fraud / %d legitimate).",
        type(model).__name__,
        len(y_train),
        int((y_train == _FRAUD_LABEL).sum()),
        int((y_train == _LEGIT_LABEL).sum()),
    )
    return model


def train_xgboost_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = RANDOM_STATE,
) -> "XGBClassifier":
    """
    Build and train an XGBoost classifier on *training data only*.

    Combines :func:`calculate_scale_pos_weight`, :func:`build_xgboost_classifier`,
    and :func:`train_model` into a single call for the common case.

    Parameters
    ----------
    X_train:
        Pre-processed feature matrix (output of Day 3 preprocessing).
        Must not contain the ``Class`` column.
    y_train:
        Binary training labels.  Used to compute ``scale_pos_weight`` and
        as the fit target.  The validation set is **never** touched here.
    random_state:
        Reproducibility seed.  Defaults to ``42``.

    Returns
    -------
    XGBClassifier
        Fitted classifier ready for ``predict_proba`` / ``predict``.

    Raises
    ------
    ImportError
        If ``xgboost`` is not installed.
    TypeError / ValueError
        Propagated from :func:`validate_training_data` and
        :func:`calculate_scale_pos_weight`.

    Examples
    --------
    >>> model = train_xgboost_model(X_train, y_train)
    >>> proba = model.predict_proba(X_val)[:, 1]   # fraud probability column
    """
    _require_xgboost()

    logger.info("Training XGBoost model  (rows=%d)  …", len(X_train))

    spw = calculate_scale_pos_weight(y_train)
    clf = build_xgboost_classifier(spw, random_state=random_state)
    train_model(clf, X_train, y_train)

    logger.info("XGBoost training complete.")
    return clf


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_model(
    model: Any,
    output_path: str | Path,
) -> Path:
    """
    Save a fitted model to disk using :mod:`joblib`.

    Parameters
    ----------
    model:
        A fitted estimator.
    output_path:
        Destination file path.  The conventional name for XGBoost is
        ``artifacts/models/xgboost_baseline.joblib``.  The parent directory
        is created automatically if it does not exist.

    Returns
    -------
    Path
        Resolved path of the saved artifact.

    Raises
    ------
    ValueError
        If *model* is ``None``.
    OSError
        If the file cannot be written (permissions, disk space, etc.).

    Examples
    --------
    >>> path = save_model(clf, "artifacts/models/xgboost_baseline.joblib")
    >>> print(path)
    PosixPath('.../artifacts/models/xgboost_baseline.joblib')
    """
    if model is None:
        raise ValueError("model is None — pass a fitted estimator to save_model.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, output_path)
    write_checksum_sidecar(output_path)
    logger.info(
        "Saved %s → %s", type(model).__name__, output_path
    )
    return output_path.resolve()


def load_model(model_path: str | Path) -> Any:
    """
    Load a model artifact from disk.

    Parameters
    ----------
    model_path:
        Path to a ``.joblib`` file previously created by :func:`save_model`.

    Returns
    -------
    object
        The deserialised estimator.

    Raises
    ------
    FileNotFoundError
        If *model_path* does not exist.

    Examples
    --------
    >>> clf = load_model("artifacts/models/xgboost_baseline.joblib")
    >>> proba = clf.predict_proba(X_val)[:, 1]
    """
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model artifact not found at '{model_path}'.  "
            "Run the Day 5 pipeline first:\n\n"
            "    python -m scripts.run_day5_advanced_models"
        )

    trusted_root = model_path.parent.parent if model_path.parent.name == "models" else model_path.parent
    model = load_verified_joblib(
        model_path,
        trusted_root=trusted_root,
        required_attributes=("predict_proba",),
    )
    logger.info("Loaded %s ← %s", type(model).__name__, model_path)
    return model


# ---------------------------------------------------------------------------
# Feature importances
# ---------------------------------------------------------------------------


def get_feature_importances(
    model: Any,
    feature_names: list[str] | None = None,
) -> pd.Series:
    """
    Return feature importances as a ranked :class:`~pandas.Series`.

    Works for any scikit-learn–compatible estimator that exposes a
    ``feature_importances_`` attribute (XGBoost, Random Forest, etc.).

    Parameters
    ----------
    model:
        A fitted estimator with a ``feature_importances_`` attribute.
    feature_names:
        Column names corresponding to the importances array.  If ``None``,
        the model's ``feature_names_in_`` attribute is used when available,
        otherwise generic ``feature_0``, ``feature_1``, … labels are applied.

    Returns
    -------
    pd.Series
        Importances indexed by feature name, sorted descending.

    Raises
    ------
    AttributeError
        If the model does not expose ``feature_importances_``.

    Notes
    -----
    XGBoost's default importance type is ``"weight"`` (number of times a
    feature appears in trees).  This is useful for a quick overview but
    differs from SHAP-based importances (Day 7 scope).
    """
    if not hasattr(model, "feature_importances_"):
        raise AttributeError(
            f"{type(model).__name__} does not have a 'feature_importances_' "
            "attribute.  Only tree-based models support this method."
        )

    importances: np.ndarray = model.feature_importances_

    if feature_names is None:
        # Use model's stored feature names when available (scikit-learn ≥ 1.0)
        if hasattr(model, "feature_names_in_"):
            feature_names = list(model.feature_names_in_)
        else:
            feature_names = [f"feature_{i}" for i in range(len(importances))]

    if len(feature_names) != len(importances):
        raise ValueError(
            f"feature_names has {len(feature_names)} entries but model has "
            f"{len(importances)} importances.  They must have the same length."
        )

    series = pd.Series(importances, index=feature_names, name="importance")
    return series.sort_values(ascending=False)


# ---------------------------------------------------------------------------
# Summary helper
# ---------------------------------------------------------------------------


def get_model_info(model: Any) -> dict[str, Any]:
    """
    Return a lightweight summary dict for a fitted XGBoost model.

    Useful for logging and report generation.

    Parameters
    ----------
    model:
        A fitted :class:`xgboost.XGBClassifier` (or compatible estimator).

    Returns
    -------
    dict
        Keys: ``model_type``, ``n_estimators``, ``max_depth``,
        ``learning_rate``, ``scale_pos_weight``, ``random_state``,
        ``n_features``, ``has_feature_importances``.
    """
    params = model.get_params() if hasattr(model, "get_params") else {}

    return {
        "model_type": type(model).__name__,
        "n_estimators": params.get("n_estimators"),
        "max_depth": params.get("max_depth"),
        "learning_rate": params.get("learning_rate"),
        "scale_pos_weight": params.get("scale_pos_weight"),
        "random_state": params.get("random_state"),
        "n_features": (
            len(model.feature_names_in_)
            if hasattr(model, "feature_names_in_")
            else None
        ),
        "has_feature_importances": hasattr(model, "feature_importances_"),
    }


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(
        "advanced_models.py is a library module.\n"
        "It is intended to be called by:\n\n"
        "    python -m scripts.run_day5_advanced_models\n\n"
        "or imported directly:\n\n"
        "    from src.models.advanced_models import train_xgboost_model"
    )
