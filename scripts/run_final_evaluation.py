"""Guard the already-observed historical test result against accidental reuse.

The historical implementation was intentionally disabled. New scientific
decisions use development/forward evaluation. This command can verify existing
evidence but cannot load test rows, score a model, or overwrite reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.historical_lock import (  # noqa: E402
    HistoricalObservationError,
    verify_historical_observation,
)
from src.utils.config import load_project_config  # noqa: E402

PROJECT_CONFIG = load_project_config()


def verify_existing_evidence() -> dict[str, object]:
    """Verify the immutable historical observation without evaluating data."""
    payload = verify_historical_observation(
        PROJECT_CONFIG.reports.historical_lock,
        PROJECT_ROOT,
    )
    return {
        "evaluation_scope": payload["evaluation_scope"],
        "files_verified": len(payload["files"]),
        "status": "locked_historical_observation_verified",
    }


def run_final_evaluation(*_args: object, **_kwargs: object) -> NoReturn:
    """Refuse to rerun the random test after verifying its tracked evidence."""
    try:
        verify_existing_evidence()
    except HistoricalObservationError as exc:
        raise HistoricalObservationError(
            "Historical evidence verification failed; do not rerun or replace it. "
            f"Restore the tracked files first: {exc}"
        ) from exc
    raise HistoricalObservationError(
        "The random held-out test result is already observed and tracked by a SHA-256 lock. "
        "It must not be rerun for tuning or overwritten. Use development/forward evaluation "
        "for new decisions."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the tracked historical files; never rerun evaluation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        print(json.dumps(verify_existing_evidence(), sort_keys=True))
        return 0
    run_final_evaluation()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HistoricalObservationError as exc:
        print(f"Historical evaluation locked: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
