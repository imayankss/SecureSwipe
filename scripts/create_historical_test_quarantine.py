"""Create the ignored hash-only manifest for the locked historical test rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.historical_quarantine import (  # noqa: E402
    write_historical_quarantine_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x-test", required=True, type=Path)
    parser.add_argument("--y-test", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = write_historical_quarantine_manifest(
        x_test_path=args.x_test,
        y_test_path=args.y_test,
        output_path=args.output,
    )
    print(json.dumps({"historical_quarantine": str(manifest)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
