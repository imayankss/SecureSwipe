#!/usr/bin/env python3
"""Explicitly verify the configured postgres-scale audit chain."""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.postgres_audit import (  # noqa: E402
    PostgresAuditIntegrityError,
    verify_audit_chain,
)
from api.postgres_migrations import MigrationError, run_migrations  # noqa: E402
from api.scale_config import (  # noqa: E402
    PostgresScaleSettings,
    ScaleConfigurationError,
)


async def _verify(settings: PostgresScaleSettings) -> int:
    await run_migrations(
        dsn=settings.dsn,
        schema=settings.schema,
        apply=False,
        connect_timeout_seconds=settings.connect_timeout_seconds,
    )
    connection = await psycopg.AsyncConnection.connect(
        settings.dsn,
        autocommit=True,
        connect_timeout=max(1, math.ceil(settings.connect_timeout_seconds)),
    )
    try:
        result = await verify_audit_chain(connection, schema=settings.schema)
    finally:
        await connection.close()
    print(
        "PostgreSQL audit chain verified: "
        f"events={result.event_count} last_sequence={result.last_sequence}"
    )
    return 0


def main() -> int:
    try:
        settings = PostgresScaleSettings.from_environment()
        return asyncio.run(_verify(settings))
    except (
        MigrationError,
        PostgresAuditIntegrityError,
        ScaleConfigurationError,
        psycopg.Error,
        OSError,
    ) as exc:
        print(f"PostgreSQL audit verification failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
