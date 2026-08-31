"""Forward-only, checksum-verified PostgreSQL migrations for postgres-scale."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

MIGRATION_LOCK_ID = 6000276099173077847
DEFAULT_MIGRATION_DIRECTORY = Path(__file__).parent / "migrations" / "postgres"
_MIGRATION_PATTERN = re.compile(r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    """Base class for migration integrity and availability failures."""


class MigrationIntegrityError(MigrationError):
    """Raised when code and recorded migration history are incompatible."""


class MigrationRequiredError(MigrationError):
    """Raised by check mode when an explicit migration apply is still required."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    checksum_sha256: str
    statement: str


def load_migrations(directory: Path = DEFAULT_MIGRATION_DIRECTORY) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_PATTERN.fullmatch(path.name)
        if match is None:
            raise MigrationIntegrityError(f"Invalid migration filename: {path.name}")
        encoded = path.read_bytes()
        migrations.append(
            Migration(
                version=int(match.group("version")),
                name=match.group("name"),
                checksum_sha256=hashlib.sha256(encoded).hexdigest(),
                statement=encoded.decode("utf-8"),
            )
        )
    if not migrations:
        raise MigrationIntegrityError("No PostgreSQL migrations were found.")
    expected = list(range(1, len(migrations) + 1))
    if [migration.version for migration in migrations] != expected:
        raise MigrationIntegrityError("PostgreSQL migration versions must be contiguous from 0001.")
    return tuple(migrations)


async def _set_search_path(connection: psycopg.AsyncConnection[Any], schema: str) -> None:
    await connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))


async def _bootstrap_history(
    connection: psycopg.AsyncConnection[Any], schema: str
) -> None:
    async with connection.transaction():
        await connection.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
        )
        await _set_search_path(connection, schema)
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS secureswipe_schema_migrations (
                version integer PRIMARY KEY CHECK (version > 0),
                name text NOT NULL UNIQUE,
                checksum_sha256 char(64) NOT NULL
                    CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
                applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
            )
            """
        )


async def _history_exists(
    connection: psycopg.AsyncConnection[Any], schema: str
) -> bool:
    cursor = await connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = %s
              AND relation.relname = 'secureswipe_schema_migrations'
              AND relation.relkind = 'r'
        )
        """,
        (schema,),
    )
    row = await cursor.fetchone()
    return bool(row and row[0])


async def _recorded_migrations(
    connection: psycopg.AsyncConnection[Any], schema: str
) -> list[tuple[int, str, str]]:
    async with connection.transaction():
        await _set_search_path(connection, schema)
        cursor = await connection.execute(
            """
            SELECT version, name, checksum_sha256
            FROM secureswipe_schema_migrations
            ORDER BY version
            """
        )
        return [(int(row[0]), str(row[1]), str(row[2])) for row in await cursor.fetchall()]


async def _grant_application_privileges(
    connection: psycopg.AsyncConnection[Any], *, schema: str, application_role: str
) -> None:
    """Grant only the operations required by the runtime transaction path."""
    if not application_role.strip():
        raise MigrationIntegrityError("The PostgreSQL application role is empty.")
    role = sql.Identifier(application_role)
    namespace = sql.Identifier(schema)
    async with connection.transaction():
        await connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(namespace, role)
        )
        await connection.execute(
            sql.SQL("GRANT SELECT ON {}.secureswipe_schema_migrations TO {}").format(
                namespace, role
            )
        )
        await connection.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE ON {}.secureswipe_idempotency TO {}"
            ).format(namespace, role)
        )
        await connection.execute(
            sql.SQL("GRANT SELECT, UPDATE ON {}.audit_chain_heads TO {}").format(
                namespace, role
            )
        )
        await connection.execute(
            sql.SQL("REVOKE ALL ON {}.audit_events FROM PUBLIC").format(namespace)
        )
        await connection.execute(
            sql.SQL("REVOKE UPDATE, DELETE, TRUNCATE ON {}.audit_events FROM {}").format(
                namespace, role
            )
        )
        await connection.execute(
            sql.SQL("GRANT SELECT, INSERT ON {}.audit_events TO {}").format(
                namespace, role
            )
        )
        privilege_cursor = await connection.execute(
            """
            SELECT
                has_table_privilege(%s, %s, 'UPDATE'),
                has_table_privilege(%s, %s, 'DELETE'),
                has_table_privilege(%s, %s, 'TRUNCATE')
            """,
            (application_role, f"{schema}.audit_events") * 3,
        )
        privileges = await privilege_cursor.fetchone()
        if privileges is None or any(bool(value) for value in privileges):
            raise MigrationIntegrityError(
                "The application role has forbidden audit-event privileges."
            )


async def _validate_role_separation(
    connection: psycopg.AsyncConnection[Any], application_role: str
) -> None:
    cursor = await connection.execute(
        """
        SELECT current_user, role.rolsuper,
               pg_has_role(%s, current_user, 'MEMBER')
        FROM pg_catalog.pg_roles AS role
        WHERE role.rolname = %s
        """,
        (application_role, application_role),
    )
    row = await cursor.fetchone()
    if row is None:
        raise MigrationIntegrityError("The PostgreSQL application role does not exist.")
    if application_role == str(row[0]) or bool(row[1]) or bool(row[2]):
        raise MigrationIntegrityError(
            "Migration owner and application role must be separate non-superuser roles."
        )


def _validate_history(
    recorded: list[tuple[int, str, str]], migrations: tuple[Migration, ...]
) -> None:
    if len(recorded) > len(migrations):
        raise MigrationIntegrityError("Database schema is newer than this application.")
    for index, (version, name, checksum) in enumerate(recorded):
        expected = migrations[index]
        if version != expected.version or name != expected.name:
            raise MigrationIntegrityError("Migration history is missing, unknown, or reordered.")
        if checksum != expected.checksum_sha256:
            raise MigrationIntegrityError(
                f"Migration {version:04d}_{name} has a checksum mismatch."
            )


async def run_migrations(
    *,
    dsn: str,
    schema: str,
    apply: bool,
    connect_timeout_seconds: float = 2.0,
    migration_directory: Path = DEFAULT_MIGRATION_DIRECTORY,
    application_role: str | None = None,
) -> tuple[int, ...]:
    """Check or explicitly apply migrations under a session advisory lock."""
    migrations = load_migrations(migration_directory)
    try:
        connection = await psycopg.AsyncConnection.connect(
            dsn,
            autocommit=True,
            connect_timeout=max(1, math.ceil(connect_timeout_seconds)),
        )
    except (psycopg.Error, OSError) as exc:
        raise MigrationError("PostgreSQL migration connection failed.") from exc
    try:
        await connection.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
        if application_role is not None:
            await _validate_role_separation(connection, application_role)
        history_exists = await _history_exists(connection, schema)
        if not history_exists and not apply:
            raise MigrationRequiredError(
                "PostgreSQL migrations require explicit application."
            )
        if not history_exists:
            await _bootstrap_history(connection, schema)
        recorded = await _recorded_migrations(connection, schema)
        _validate_history(recorded, migrations)
        pending = migrations[len(recorded) :]
        if pending and not apply:
            raise MigrationRequiredError(
                f"{len(pending)} PostgreSQL migration(s) require explicit application."
            )
        applied: list[int] = []
        for migration in pending:
            async with connection.transaction():
                await _set_search_path(connection, schema)
                await connection.execute(migration.statement)
                await connection.execute(
                    """
                    INSERT INTO secureswipe_schema_migrations
                        (version, name, checksum_sha256)
                    VALUES (%s, %s, %s)
                    """,
                    (migration.version, migration.name, migration.checksum_sha256),
                )
            applied.append(migration.version)
        if application_role is not None:
            await _grant_application_privileges(
                connection, schema=schema, application_role=application_role
            )
        return tuple(applied)
    except MigrationError:
        raise
    except (psycopg.Error, UnicodeError) as exc:
        raise MigrationError("PostgreSQL migration operation failed.") from exc
    finally:
        try:
            await connection.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
        finally:
            await connection.close()
