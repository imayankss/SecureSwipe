from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.data_loader import load_credit_card_data, summarize_dataset  # noqa: E402
from src.eda.eda_report import save_day2_eda_report  # noqa: E402
from src.eda.imbalance_analysis import (  # noqa: E402
    format_imbalance_summary_for_console,
    generate_imbalance_summary,
)
from src.eda.visualizations import generate_all_eda_figures  # noqa: E402
from src.utils.config import load_project_config  # noqa: E402

PROJECT_CONFIG = load_project_config()
DEFAULT_DATA_PATH = PROJECT_CONFIG.data.raw_path
DEFAULT_REPORT_PATH = Path("reports/day2_eda_summary.md")
DEFAULT_FIGURES_DIR = PROJECT_CONFIG.reports.figures_dir


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Day 2 EDA runner.

    Returns:
        The parsed argparse Namespace.
    """
    parser = argparse.ArgumentParser(
        description="Run Day 2 EDA for the Credit Card Fraud Detection & Risk Scoring System."
    )
    parser.add_argument(
        "--data-path",
        type=str,
        default=str(DEFAULT_DATA_PATH),
        help="Path to the raw creditcard.csv dataset.",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        default=str(DEFAULT_REPORT_PATH),
        help="Path to save the Day 2 EDA Markdown report.",
    )
    parser.add_argument(
        "--figures-dir",
        type=str,
        default=str(DEFAULT_FIGURES_DIR),
        help="Directory to save generated EDA figures.",
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Skip generating EDA figures.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip dataset schema validation when loading the dataset.",
    )

    return parser.parse_args()


def run_day2_eda(
    data_path: str | Path = DEFAULT_DATA_PATH,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    figures_dir: str | Path = DEFAULT_FIGURES_DIR,
    generate_figures: bool = True,
    validate: bool = True,
) -> dict[str, object]:
    """Run the full Day 2 EDA workflow.

    Loads the dataset, summarizes it, analyzes class imbalance, optionally
    generates EDA figures, and saves a Markdown EDA report.

    Args:
        data_path: Path to the raw creditcard.csv dataset.
        report_path: Path to save the Day 2 EDA Markdown report.
        figures_dir: Directory to save generated EDA figures.
        generate_figures: Whether to generate EDA figures.
        validate: Whether to validate the dataset schema when loading.

    Returns:
        A dictionary containing dataset_shape, dataset_summary,
        imbalance_summary, figure_paths, and report_path.
    """
    print("Dataset loading started...")
    df = load_credit_card_data(data_path=data_path, validate=validate)
    print(f"Dataset loaded successfully. Shape: {df.shape}")

    dataset_summary = summarize_dataset(df)

    print("\nAnalyzing class imbalance...")
    imbalance_summary = generate_imbalance_summary(df)
    print(format_imbalance_summary_for_console(imbalance_summary))

    figure_paths: dict[str, Path] = {}
    if generate_figures:
        print("\nGenerating EDA figures...")
        figure_paths = generate_all_eda_figures(df, output_dir=figures_dir)
        print(f"Figures saved to: {Path(figures_dir).resolve()}")
    else:
        print("\nSkipping figure generation (--skip-figures was set).")

    print("\nGenerating Day 2 EDA report...")
    saved_report_path = save_day2_eda_report(
        df=df,
        imbalance_summary=imbalance_summary,
        figure_paths=figure_paths if figure_paths else None,
        report_path=report_path,
    )
    print(f"Report saved to: {saved_report_path.resolve()}")

    return {
        "dataset_shape": df.shape,
        "dataset_summary": dataset_summary,
        "imbalance_summary": imbalance_summary,
        "figure_paths": figure_paths,
        "report_path": saved_report_path,
    }


def print_success_message(results: dict[str, object]) -> None:
    """Print a clean summary of the completed Day 2 EDA run.

    Args:
        results: The dictionary returned by run_day2_eda().
    """
    print("\n" + "=" * 50)
    print("Day 2 EDA completed successfully.")
    print("=" * 50)
    print(f"Dataset shape: {results.get('dataset_shape')}")
    print(f"Report path: {results.get('report_path')}")

    figure_paths = results.get("figure_paths") or {}
    if figure_paths:
        print("Generated figures:")
        for name, path in figure_paths.items():
            print(f"  - {name}: {path}")
    else:
        print("No figures were generated for this run.")

    print("\nReminder: Day 2 covers EDA and class imbalance analysis only.")
    print("Model training, preprocessing, and threshold tuning are not part of Day 2.")


def main() -> None:
    """Parse arguments, run Day 2 EDA, and report success or failure."""
    print(
        "Direct unmanifested execution is disabled. Use "
        "`python scripts/run_reference_stage.py --stage day2 --output-dir <new-dir>`. ",
        file=sys.stderr,
    )
    raise SystemExit(2)

    args = parse_args()

    try:
        results = run_day2_eda(
            data_path=args.data_path,
            report_path=args.report_path,
            figures_dir=args.figures_dir,
            generate_figures=not args.skip_figures,
            validate=not args.no_validate,
        )
        print_success_message(results)
    except FileNotFoundError as error:
        print(f"\nFile not found: {error}")
        sys.exit(1)
    except ValueError as error:
        print(f"\nValidation error: {error}")
        sys.exit(1)
    except Exception as error:  # noqa: BLE001
        print(f"\nAn unexpected error occurred: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
