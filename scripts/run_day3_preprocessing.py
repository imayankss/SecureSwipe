"""
Day 3 orchestration script for the
Credit Card Fraud Detection & Risk Scoring System.

Runs the full Day 3 preprocessing workflow from the repo root:

    python3 scripts/run_day3_preprocessing.py

Workflow:
    1. Load and validate the raw dataset.
    2. Separate features (X) and target (y).
    3. Create a stratified train/validation/test split.
    4. Save interim split files and split metadata.
    5. Fit a preprocessor on training data only.
    6. Transform train/validation/test features.
    7. Save processed data and the fitted preprocessor.
    8. Generate the Day 3 preprocessing Markdown report.

No model training, evaluation, or threshold tuning happens here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Union

# ---------------------------------------------------------------------------
# Make "from src...." imports work when run as:
#   python3 scripts/run_day3_preprocessing.py
# from the repository root.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_loader import load_credit_card_data
from src.data.split_data import (
    separate_features_target,
    create_train_val_test_split,
    get_split_summary,
    save_split_data,
    save_split_metadata,
)
from src.preprocessing.preprocessors import (
    fit_transform_train_val_test,
    save_processed_data,
    save_preprocessor,
    get_preprocessing_summary,
)
from src.preprocessing.preprocessing_report import save_day3_preprocessing_report
from src.utils.config import load_project_config

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

PROJECT_CONFIG = load_project_config()
DEFAULT_DATA_PATH = PROJECT_CONFIG.data.raw_path
DEFAULT_INTERIM_DIR = PROJECT_CONFIG.data.interim_dir
DEFAULT_PROCESSED_DIR = PROJECT_CONFIG.data.processed_dir
DEFAULT_ARTIFACT_DIR = PROJECT_CONFIG.artifacts.trusted_root / "preprocessing"
DEFAULT_PREPROCESSOR_PATH = DEFAULT_ARTIFACT_DIR / "preprocessor.joblib"
DEFAULT_METADATA_PATH = DEFAULT_ARTIFACT_DIR / "split_metadata.json"
DEFAULT_REPORT_PATH: Path = Path("reports/day3_preprocessing_summary.md")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the Day 3 preprocessing script.

    Returns:
        Parsed argparse.Namespace with all configurable paths and flags.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Run the Day 3 preprocessing workflow: load and validate the "
            "raw dataset, create a stratified train/validation/test split, "
            "fit a leakage-safe preprocessor on training data, transform "
            "all splits, and generate the Day 3 report."
        )
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=str(DEFAULT_DATA_PATH),
        help="Path to the raw creditcard.csv dataset.",
    )
    parser.add_argument(
        "--interim-dir",
        type=str,
        default=str(DEFAULT_INTERIM_DIR),
        help="Directory to save raw train/validation/test split files.",
    )
    parser.add_argument(
        "--processed-dir",
        type=str,
        default=str(DEFAULT_PROCESSED_DIR),
        help="Directory to save preprocessed train/validation/test files.",
    )
    parser.add_argument(
        "--preprocessor-path",
        type=str,
        default=str(DEFAULT_PREPROCESSOR_PATH),
        help="Path to save the fitted preprocessor artifact.",
    )
    parser.add_argument(
        "--metadata-path",
        type=str,
        default=str(DEFAULT_METADATA_PATH),
        help="Path to save the split metadata JSON file.",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=str(DEFAULT_REPORT_PATH),
        help="Path to save the Day 3 preprocessing Markdown report.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip dataset schema/quality validation when loading the raw data.",
    )
    return parser.parse_args()


def run_day3_preprocessing(
    data_path: Union[str, Path] = DEFAULT_DATA_PATH,
    interim_dir: Union[str, Path] = DEFAULT_INTERIM_DIR,
    processed_dir: Union[str, Path] = DEFAULT_PROCESSED_DIR,
    preprocessor_path: Union[str, Path] = DEFAULT_PREPROCESSOR_PATH,
    metadata_path: Union[str, Path] = DEFAULT_METADATA_PATH,
    report_path: Union[str, Path] = DEFAULT_REPORT_PATH,
    validate: bool = True,
) -> Dict[str, Any]:
    """
    Run the complete Day 3 preprocessing and splitting workflow.

    Args:
        data_path: Path to the raw creditcard.csv dataset.
        interim_dir: Directory to save raw split files.
        processed_dir: Directory to save preprocessed split files.
        preprocessor_path: Path to save the fitted preprocessor artifact.
        metadata_path: Path to save split metadata JSON.
        report_path: Path to save the Day 3 Markdown report.
        validate: Whether to validate the dataset schema/quality on load.

    Returns:
        A dictionary with keys: "dataset_shape", "split_summary",
        "preprocessing_summary", "interim_paths", "processed_paths",
        "artifact_paths", and "report_path".
    """
    data_path = Path(data_path)
    interim_dir = Path(interim_dir)
    processed_dir = Path(processed_dir)
    preprocessor_path = Path(preprocessor_path)
    metadata_path = Path(metadata_path)
    report_path = Path(report_path)

    print("Step 1/8: Loading and validating the raw dataset...")
    df = load_credit_card_data(data_path, validate=validate)
    dataset_shape = df.shape
    print(f"  Loaded dataset with shape {dataset_shape}.")

    print("Step 2/8: Separating features (X) and target (y)...")
    X, y = separate_features_target(df)
    print(f"  X shape: {X.shape}, y shape: {y.shape}.")

    print("Step 3/8: Creating stratified train/validation/test split...")
    splits = create_train_val_test_split(X, y)
    print(
        f"  Train rows: {splits['X_train'].shape[0]}, "
        f"Validation rows: {splits['X_val'].shape[0]}, "
        f"Test rows: {splits['X_test'].shape[0]}."
    )

    print("Step 4/8: Generating split summary...")
    split_summary = get_split_summary(splits)

    print("Step 5/8: Saving interim split files and split metadata...")
    interim_paths = save_split_data(splits, output_dir=interim_dir)
    saved_metadata_path = save_split_metadata(split_summary, metadata_path=metadata_path)

    print("Step 6/8: Fitting preprocessor on training data and transforming all splits...")
    preprocessing_results = fit_transform_train_val_test(
        splits["X_train"], splits["X_val"], splits["X_test"]
    )

    print("Step 7/8: Saving processed data and the fitted preprocessor...")
    processed_paths = save_processed_data(
        preprocessing_results["X_train_processed"],
        preprocessing_results["X_val_processed"],
        preprocessing_results["X_test_processed"],
        splits["y_train"],
        splits["y_val"],
        splits["y_test"],
        output_dir=processed_dir,
    )
    saved_preprocessor_path = save_preprocessor(
        preprocessing_results["preprocessor"], output_path=preprocessor_path
    )

    preprocessing_summary = get_preprocessing_summary(
        splits["X_train"],
        preprocessing_results["X_train_processed"],
        preprocessing_results["feature_names"],
    )

    artifact_paths: Dict[str, Path] = {
        "preprocessor": saved_preprocessor_path,
        "split_metadata": saved_metadata_path,
    }

    print("Step 8/8: Generating the Day 3 preprocessing report...")
    saved_report_path = save_day3_preprocessing_report(
        split_summary=split_summary,
        preprocessing_summary=preprocessing_summary,
        interim_paths=interim_paths,
        processed_paths=processed_paths,
        artifact_paths=artifact_paths,
        report_path=report_path,
    )

    return {
        "dataset_shape": dataset_shape,
        "split_summary": split_summary,
        "preprocessing_summary": preprocessing_summary,
        "interim_paths": interim_paths,
        "processed_paths": processed_paths,
        "artifact_paths": artifact_paths,
        "report_path": saved_report_path,
    }


def print_success_message(results: Dict[str, Any]) -> None:
    """
    Print a clean summary message after a successful Day 3 run.

    Args:
        results: The dictionary returned by run_day3_preprocessing.
    """
    split_summary = results.get("split_summary", {})
    artifact_paths = results.get("artifact_paths", {})

    print("\n" + "=" * 70)
    print("Day 3 preprocessing completed successfully.")
    print("=" * 70)
    print(f"Dataset shape: {results.get('dataset_shape')}")
    print(f"Train rows: {split_summary.get('train_rows')}")
    print(f"Validation rows: {split_summary.get('validation_rows')}")
    print(f"Test rows: {split_summary.get('test_rows')}")
    print(f"Report saved to: {results.get('report_path')}")
    print(f"Preprocessor saved to: {artifact_paths.get('preprocessor')}")
    print(f"Split metadata saved to: {artifact_paths.get('split_metadata')}")
    print("\nReminder: No model training was performed in this step.")
    print("=" * 70)


def main() -> None:
    """Parse arguments, run the Day 3 pipeline, and report the outcome."""
    args = parse_args()

    try:
        results = run_day3_preprocessing(
            data_path=args.data_path,
            interim_dir=args.interim_dir,
            processed_dir=args.processed_dir,
            preprocessor_path=args.preprocessor_path,
            metadata_path=args.metadata_path,
            report_path=args.report_path,
            validate=not args.no_validate,
        )
        print_success_message(results)
    except FileNotFoundError as error:
        print(f"\nFile not found: {error}", file=sys.stderr)
        sys.exit(1)
    except ValueError as error:
        print(f"\nInvalid data or configuration: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - top-level CLI safety net
        print(f"\nUnexpected error during Day 3 preprocessing: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
