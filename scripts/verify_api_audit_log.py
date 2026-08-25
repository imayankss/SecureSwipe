"""Verify SecureSwipe's tamper-evident append-only API audit evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.audit import verify_audit_log  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_path", type=Path)
    parser.add_argument("--anchor-path", type=Path)
    args = parser.parse_args()
    result = verify_audit_log(args.log_path, anchor_path=args.anchor_path)
    event_label = "event" if result.event_count == 1 else "events"
    print(
        "Verified tamper-evident append-only audit evidence: "
        f"{result.event_count} {event_label}; head {result.head_event_hash}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
