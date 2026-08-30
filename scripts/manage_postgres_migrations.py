#!/usr/bin/env python3
"""Explicit operator command for postgres-scale migration apply/check."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.postgres_migrations import MigrationError, run_migrations  # noqa: E402
from api.scale_config import (  # noqa: E402
    PostgresScaleSettings,
    ScaleConfigurationError,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--apply", action="store_true", help="Apply pending migrations.")
    action.add_argument("--check", action="store_true", help="Require all migrations applied.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = PostgresScaleSettings.from_environment()
        migration_dsn = os.getenv("SECURESWIPE_POSTGRES_MIGRATION_DSN", "").strip()
        application_role = os.getenv(
            "SECURESWIPE_POSTGRES_APPLICATION_ROLE", ""
        ).strip()
        if args.apply and not migration_dsn:
            raise ScaleConfigurationError(
                "SECURESWIPE_POSTGRES_MIGRATION_DSN is required for --apply."
            )
        if args.apply and not application_role:
            raise ScaleConfigurationError(
                "SECURESWIPE_POSTGRES_APPLICATION_ROLE is required for --apply."
            )
        applied = asyncio.run(
            run_migrations(
                dsn=migration_dsn or settings.dsn,
                schema=settings.schema,
                apply=args.apply,
                connect_timeout_seconds=settings.connect_timeout_seconds,
                application_role=application_role or None,
            )
        )
    except (ScaleConfigurationError, MigrationError) as exc:
        print(f"PostgreSQL migration {('apply' if args.apply else 'check')} failed: {exc}")
        return 1
    if applied:
        print(f"Applied PostgreSQL migration versions: {', '.join(map(str, applied))}")
    else:
        print("PostgreSQL migrations are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
