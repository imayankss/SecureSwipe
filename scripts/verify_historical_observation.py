"""Verify the locked, already-observed historical test evidence without rerunning it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.historical_lock import verify_historical_observation
from src.utils.config import load_project_config


def main() -> int:
    config = load_project_config()
    payload = verify_historical_observation(config.reports.historical_lock, PROJECT_ROOT)
    print(
        json.dumps(
            {
                "evaluation_scope": payload["evaluation_scope"],
                "files_verified": len(payload["files"]),
                "status": "locked_historical_observation_verified",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
