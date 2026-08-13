"""Baseline model creation, training, saving, and loading utilities.

This module provides the Day 4 baseline models for the Credit Card Fraud
Detection & Risk Scoring System:

- DummyClassifier (naive majority-class baseline)
- LogisticRegression (simple linear baseline)
- RandomForestClassifier (nonlinear tree-based baseline)

These models establish a benchmark before training advanced boosting
models (XGBoost / LightGBM) on later days. No hyperparameter tuning,
threshold tuning, or test-set evaluation is performed here.
"""

from pathlib import Path
from typing import Any, Dict

import joblib
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from src.artifacts.bundle import load_verified_joblib, write_checksum_sidecar
from src.preprocessing.feature_config import RANDOM_STATE

DEFAULT_MODELS_DIR: Path = Path("artifacts/models")


def create_dummy_baseline(random_state: int = RANDOM_STATE) -> DummyClassifier:
    """Create a naive baseline classifier that always predicts the majority class.

    This baseline is useful to demonstrate why accuracy is a misleading
    metric for highly imbalanced fraud detection problems: a model that
    never predicts fraud can still achieve very high accuracy.

    Args:
        random_state: Random seed for reproducibility (unused by
            DummyClassifier with strategy="most_frequent" but kept for a
            consistent function signature across baseline factories).

    Returns:
        An unfitted DummyClassifier configured with strategy="most_frequent".
    """
    return DummyClassifier(strategy="most_frequent", random_state=random_state)


def create_logistic_regression_baseline(
    random_state: int = RANDOM_STATE,
) -> LogisticRegression:
    """Create a simple, interpretable Logistic Regression baseline model.

    Uses balanced class weights to help the model account for the rarity
    of the fraud class without resampling the training data.

    Args:
        random_state: Random seed for reproducibility.

    Returns:
        An unfitted LogisticRegression model.
    """
    return LogisticRegression(
        class_weight="balanced",
        max_iter=1000,
        solver="lbfgs",
        random_state=random_state,
    )


def create_random_forest_baseline(
    random_state: int = RANDOM_STATE,
) -> RandomForestClassifier:
    """Create a non-linear, tree-based Random Forest baseline model.

    This baseline uses default-style hyperparameters (no tuning) and
    balanced class weights to address class imbalance.

    Args:
        random_state: Random seed for reproducibility.

    Returns:
        An unfitted RandomForestClassifier.
    """
    return RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
        max_depth=None,
    )


def get_baseline_models(random_state: int = RANDOM_STATE) -> Dict[str, Any]:
    """Create all Day 4 baseline models.

    Args:
        random_state: Random seed used for every baseline model.

    Returns:
        A dictionary mapping baseline model names to unfitted model
        instances:
        {
            "dummy_baseline": DummyClassifier,
            "logistic_regression": LogisticRegression,
            "random_forest": RandomForestClassifier,
        }
    """
    return {
        "dummy_baseline": create_dummy_baseline(random_state=random_state),
        "logistic_regression": create_logistic_regression_baseline(
            random_state=random_state
        ),
        "random_forest": create_random_forest_baseline(random_state=random_state),
    }


def validate_training_data(X_train: pd.DataFrame, y_train: pd.Series) -> None:
    """Validate that training features and target are safe to train on.

    Args:
        X_train: Training feature matrix.
        y_train: Training target vector (Class column).

    Raises:
        ValueError: If any validation check fails.
    """
    if X_train is None or X_train.empty:
        raise ValueError("X_train is empty. Cannot train a model on no data.")

    if y_train is None or y_train.empty:
        raise ValueError("y_train is empty. Cannot train a model on no data.")

    if len(X_train) != len(y_train):
        raise ValueError(
            f"X_train has {len(X_train)} rows but y_train has {len(y_train)} "
            "rows. They must match."
        )

    if "Class" in X_train.columns:
        raise ValueError(
            "X_train contains the 'Class' target column. This indicates "
            "target leakage and must be removed before training."
        )

    unique_labels = set(pd.Series(y_train).unique().tolist())
    if not unique_labels.issubset({0, 1}):
        raise ValueError(
            f"y_train must contain only 0 and 1, but found: {unique_labels}"
        )

    if len(unique_labels) < 2:
        raise ValueError(
            "y_train must contain both classes (0 and 1), but only found: "
            f"{unique_labels}"
        )

    non_numeric_columns = X_train.select_dtypes(exclude="number").columns.tolist()
    if non_numeric_columns:
        raise ValueError(
            f"X_train contains non-numeric columns: {non_numeric_columns}. "
            "All features must be numeric before training."
        )

    if X_train.isnull().values.any():
        raise ValueError("X_train contains missing values. Please impute or drop them first.")

    if pd.Series(y_train).isnull().any():
        raise ValueError("y_train contains missing values. Please clean the target first.")


def train_model(model: Any, X_train: pd.DataFrame, y_train: pd.Series) -> Any:
    """Validate training data and fit a single model.

    Args:
        model: An unfitted scikit-learn-compatible classifier.
        X_train: Training feature matrix.
        y_train: Training target vector.

    Returns:
        The fitted model.
    """
    validate_training_data(X_train, y_train)
    model.fit(X_train, y_train)
    return model


def train_baseline_models(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = RANDOM_STATE,
) -> Dict[str, Any]:
    """Create and train all Day 4 baseline models on the training data.

    Args:
        X_train: Training feature matrix.
        y_train: Training target vector.
        random_state: Random seed used for every baseline model.

    Returns:
        A dictionary mapping baseline model names to fitted model instances.
    """
    models = get_baseline_models(random_state=random_state)

    fitted_models: Dict[str, Any] = {}
    for model_name, model in models.items():
        fitted_models[model_name] = train_model(model, X_train, y_train)

    return fitted_models


def save_model(
    model: Any,
    model_name: str,
    output_dir: str | Path = DEFAULT_MODELS_DIR,
) -> Path:
    """Save a single fitted model to disk using joblib.

    Args:
        model: A fitted model to persist.
        model_name: Name used to construct the output file name.
        output_dir: Directory where the model file will be saved.

    Returns:
        The path where the model was saved.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{model_name}.joblib"
    joblib.dump(model, output_path)
    write_checksum_sidecar(output_path)
    return output_path


def save_models(
    models: Dict[str, Any],
    output_dir: str | Path = DEFAULT_MODELS_DIR,
) -> Dict[str, Path]:
    """Save multiple fitted models to disk using joblib.

    Args:
        models: A dictionary mapping model names to fitted model instances.
        output_dir: Directory where the model files will be saved.

    Returns:
        A dictionary mapping model names to their saved file paths.
    """
    saved_paths: Dict[str, Path] = {}
    for model_name, model in models.items():
        saved_paths[model_name] = save_model(model, model_name, output_dir=output_dir)
    return saved_paths


def load_model(model_path: str | Path) -> Any:
    """Load a previously saved model from disk.

    Args:
        model_path: Path to the saved joblib model file.

    Returns:
        The loaded model object.

    Raises:
        FileNotFoundError: If the model file does not exist.
    """
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model file not found at {model_path}. "
            "Please check the path or train and save the model first."
        )
    trusted_root = model_path.parent.parent if model_path.parent.name == "models" else model_path.parent
    return load_verified_joblib(
        model_path,
        trusted_root=trusted_root,
        required_attributes=("predict",),
    )


def get_model_summary(models: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize a dictionary of baseline models.

    Args:
        models: A dictionary mapping model names to model instances.

    Returns:
        A dictionary containing:
        - model_names: list of model names
        - model_count: number of models
        - model_types: dict mapping model name to its class name
        - baseline_note: explanatory note about the purpose of these models
    """
    model_names = list(models.keys())
    model_types = {name: type(model).__name__ for name, model in models.items()}

    return {
        "model_names": model_names,
        "model_count": len(model_names),
        "model_types": model_types,
        "baseline_note": (
            "These are untuned baseline models used to establish a "
            "benchmark before training advanced boosting models. They are "
            "not the final models for this project."
        ),
    }


if __name__ == "__main__":
    print(
        "This module defines baseline model utilities for the Credit Card "
        "Fraud Detection & Risk Scoring System.\n"
        "It is intended to be used by scripts/run_day4_baseline_models.py, "
        "not run directly."
    )
