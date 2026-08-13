"""Compare validated reference/current batches without logging transaction rows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.artifacts.bundle import load_model_bundle
from src.monitoring.io import write_report
from src.monitoring.offline import DriftThresholds, monitor_batches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--psi-threshold", type=float, default=0.2)
    parser.add_argument("--ks-threshold", type=float, default=0.2)
    parser.add_argument("--bins", type=int, default=10)
    parser.add_argument("--max-rows", type=int, default=1_000_000)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_rows < 1:
        raise ValueError("max_rows must be a positive integer.")
    # Bound ingestion before pandas allocates an arbitrarily large input.
    reference = pd.read_csv(args.reference, nrows=args.max_rows + 1)
    current = pd.read_csv(args.current, nrows=args.max_rows + 1)
    thresholds = DriftThresholds(
        population_stability_index=args.psi_threshold,
        ks_statistic=args.ks_threshold,
        histogram_bins=args.bins,
    )
    preflight = monitor_batches(
        reference,
        current,
        bundle=None,
        thresholds=thresholds,
        max_rows=args.max_rows,
    )
    if preflight["status"] != "valid":
        write_report(preflight, args.output, check=args.check)
        raise SystemExit(2)
    bundle = load_model_bundle(args.bundle_manifest, trusted_root=args.artifact_root)
    report = monitor_batches(
        reference,
        current,
        bundle=bundle,
        thresholds=thresholds,
        max_rows=args.max_rows,
    )
    write_report(report, args.output, check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
