"""Generate deterministic synthetic reference/current monitoring evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.create_synthetic_bundle import SYNTHETIC_MODEL_VERSION, synthetic_training_data
from src.artifacts.bundle import ModelBundle
from src.data.data_loader import fingerprint_dataframe
from src.monitoring.io import write_report
from src.monitoring.offline import monitor_batches
from src.preprocessing.feature_config import ALL_FEATURES


class _FixturePreprocessor:
    """Minimal deterministic transformer for the tracked monitoring fixture."""

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        return frame.to_numpy(dtype=float, copy=True)


class _FixtureModel:
    """Simple rule model that avoids platform-specific solver variation."""

    classes_ = np.array([0, 1])

    def predict_proba(self, values: np.ndarray) -> np.ndarray:
        positive = np.where(values[:, -1] >= 50.0, 0.8, 0.2)
        return np.column_stack((1.0 - positive, positive))


def _portable_fixture_value(value: Any) -> Any:
    """Normalize host-level floating-point noise in the tracked fixture only."""
    if isinstance(value, dict):
        return {key: _portable_fixture_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable_fixture_value(item) for item in value]
    if isinstance(value, float):
        return round(value, 12)
    return value


def _fixture_bundle(reference: pd.DataFrame, labels: np.ndarray) -> ModelBundle:
    labeled = reference.copy()
    labeled["Class"] = labels
    return ModelBundle(
        preprocessor=_FixturePreprocessor(),
        model=_FixtureModel(),
        calibrator=None,
        operating_threshold=0.53,
        feature_schema=tuple(ALL_FEATURES),
        training_data_fingerprint=fingerprint_dataframe(labeled),
        model_version=SYNTHETIC_MODEL_VERSION,
    )


def generate_demo(output: Path) -> dict[str, Any]:
    reference, labels = synthetic_training_data()
    bundle = _fixture_bundle(reference, labels)
    current = reference.copy()
    current["Amount"] = current["Amount"] * 4.0 + 100.0
    current["V1"] = current["V1"] + 3.0
    reference["Class"] = labels
    current["Class"] = labels
    report = _portable_fixture_value(monitor_batches(reference, current, bundle=bundle))
    # The tracked fixture is verified byte-for-byte on macOS and Linux. Runtime
    # provenance remains part of ordinary monitoring reports, but is host-specific
    # and therefore intentionally excluded from this synthetic demonstration.
    report.pop("runtime")
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
