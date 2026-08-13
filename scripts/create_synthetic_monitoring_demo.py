"""Generate deterministic synthetic reference/current monitoring evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.create_synthetic_bundle import build_synthetic_bundle
from src.monitoring.io import write_report
from src.monitoring.offline import monitor_batches


def generate_demo(output: Path) -> dict[str, Any]:
    bundle, _ = build_synthetic_bundle()
    from scripts.create_synthetic_bundle import synthetic_training_data

    reference, labels = synthetic_training_data()
    current = reference.copy()
    current["Amount"] = current["Amount"] * 4.0 + 100.0
    current["V1"] = current["V1"] + 3.0
    reference["Class"] = labels
    current["Class"] = labels
    report = monitor_batches(reference, current, bundle=bundle)
    write_report(report, output, check=False)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if args.check:
        temporary = output.with_suffix(output.suffix + ".check")
        try:
            generate_demo(temporary)
            if not output.is_file() or output.read_bytes() != temporary.read_bytes():
                raise RuntimeError(f"Synthetic monitoring report is stale: {output}")
        finally:
            temporary.unlink(missing_ok=True)
        return 0
    report = generate_demo(output)
    print(
        json.dumps(
            {
                "drifted_feature_count": report["feature_drift"]["drifted_feature_count"],
                "output": str(output),
                "score_drift": report["signals"]["score_drift"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
