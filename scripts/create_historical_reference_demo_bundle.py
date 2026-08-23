"""Create the strictly quarantined historical-reference demo bundle.

The tracked recipe starts unapproved.  In that state this command refuses
before it opens any supplied Parquet file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.historical_reference import create_historical_reference_demo_bundle  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an approved, quarantined historical-reference demo bundle."
    )
    parser.add_argument("--x-train", required=True, type=Path)
    parser.add_argument("--y-train", required=True, type=Path)
    parser.add_argument("--x-val", required=True, type=Path)
    parser.add_argument("--y-val", required=True, type=Path)
    parser.add_argument(
        "--historical-quarantine",
        required=True,
        type=Path,
        help="Approved hash-only historical-test quarantine manifest.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New relative directory beneath ignored artifacts/.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = create_historical_reference_demo_bundle(
        x_train=args.x_train,
        y_train=args.y_train,
        x_val=args.x_val,
        y_val=args.y_val,
        historical_quarantine=args.historical_quarantine,
        output=args.output,
    )
    print(manifest)


if __name__ == "__main__":
    main()
