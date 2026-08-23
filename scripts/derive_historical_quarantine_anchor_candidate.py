"""Print read-only review evidence for a historical-quarantine anchor candidate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.historical_quarantine import (  # noqa: E402
    build_historical_quarantine_anchor_candidate,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read and validate retained X_test/y_test Parquet files, then print "
            "an unapproved hash-only anchor candidate to stdout. This command "
            "does not write an anchor or quarantine manifest."
        )
    )
    parser.add_argument("--x-test", required=True, type=Path)
    parser.add_argument("--y-test", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidate = build_historical_quarantine_anchor_candidate(
        x_test_path=args.x_test,
        y_test_path=args.y_test,
    )
    print(json.dumps(candidate, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
