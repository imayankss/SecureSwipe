"""Explicit, secret-safe configuration for the optional PostgreSQL state profile."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

StateBackend = Literal["local-default", "postgres-scale"]

_SCHEMA_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_SCALE_ONLY_VARIABLES = (
    "SECURESWIPE_POSTGRES_DSN",
    "SECURESWIPE_POSTGRES_SCHEMA",
    "SECURESWIPE_POSTGRES_POOL_MIN_SIZE",
    "SECURESWIPE_POSTGRES_POOL_MAX_SIZE",
    "SECURESWIPE_POSTGRES_CONNECT_TIMEOUT_SECONDS",
    "SECURESWIPE_IDEMPOTENCY_HMAC_SECRET",
)


class ScaleConfigurationError(ValueError):
    """Raised for invalid scale-profile configuration without echoing secrets."""


@dataclass(frozen=True)
class PostgresScaleSettings:
    """Validated PostgreSQL settings. Secret-bearing fields are excluded from repr."""

    dsn: str = field(repr=False)
    schema: str
    hmac_secret: bytes = field(repr=False)
    pool_min_size: int = 1
    pool_max_size: int = 4
    connect_timeout_seconds: float = 2.0

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.dsn)
        except ValueError as exc:
            raise ScaleConfigurationError("SECURESWIPE_POSTGRES_DSN is invalid.") from exc
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise ScaleConfigurationError(
                "SECURESWIPE_POSTGRES_DSN must be an absolute PostgreSQL DSN."
            )
        if not parsed.path or parsed.path == "/":
            raise ScaleConfigurationError("SECURESWIPE_POSTGRES_DSN must name a database.")
        if not _SCHEMA_PATTERN.fullmatch(self.schema):
            raise ScaleConfigurationError(
                "SECURESWIPE_POSTGRES_SCHEMA must be a lowercase PostgreSQL identifier."
            )
        if len(self.hmac_secret) < 32:
            raise ScaleConfigurationError(
                "SECURESWIPE_IDEMPOTENCY_HMAC_SECRET must contain at least 32 bytes."
            )
        if not 1 <= self.pool_min_size <= self.pool_max_size <= 16:
            raise ScaleConfigurationError(
                "PostgreSQL pool sizes must satisfy 1 <= min <= max <= 16."
            )
        if not 0.1 <= self.connect_timeout_seconds <= 30.0:
            raise ScaleConfigurationError(
                "PostgreSQL connect timeout must be between 0.1 and 30.0 seconds."
            )

    @classmethod
    def from_environment(cls) -> "PostgresScaleSettings":
        dsn = os.getenv("SECURESWIPE_POSTGRES_DSN", "").strip()
        schema = os.getenv("SECURESWIPE_POSTGRES_SCHEMA", "").strip()
        secret = os.getenv("SECURESWIPE_IDEMPOTENCY_HMAC_SECRET", "")
        if not dsn:
            raise ScaleConfigurationError(
                "SECURESWIPE_POSTGRES_DSN is required for postgres-scale."
            )
        if not schema:
            raise ScaleConfigurationError(
                "SECURESWIPE_POSTGRES_SCHEMA is required for postgres-scale."
            )
        if not secret:
            raise ScaleConfigurationError(
                "SECURESWIPE_IDEMPOTENCY_HMAC_SECRET is required for postgres-scale."
            )
        try:
            pool_min = int(os.getenv("SECURESWIPE_POSTGRES_POOL_MIN_SIZE", "1"))
            pool_max = int(os.getenv("SECURESWIPE_POSTGRES_POOL_MAX_SIZE", "4"))
            timeout = float(
                os.getenv("SECURESWIPE_POSTGRES_CONNECT_TIMEOUT_SECONDS", "2.0")
            )
        except ValueError as exc:
            raise ScaleConfigurationError(
                "PostgreSQL pool and timeout settings must be numeric."
            ) from exc
        return cls(
            dsn=dsn,
            schema=schema,
            hmac_secret=secret.encode("utf-8"),
            pool_min_size=pool_min,
            pool_max_size=pool_max,
            connect_timeout_seconds=timeout,
        )


def state_backend_from_environment() -> StateBackend:
    value = os.getenv("SECURESWIPE_STATE_BACKEND", "local-default").strip()
    if value not in {"local-default", "postgres-scale"}:
        raise ScaleConfigurationError(
            "SECURESWIPE_STATE_BACKEND must be local-default or postgres-scale."
        )
    if value == "local-default" and any(os.getenv(name, "") for name in _SCALE_ONLY_VARIABLES):
        raise ScaleConfigurationError(
            "PostgreSQL settings require SECURESWIPE_STATE_BACKEND=postgres-scale."
        )
    return value  # type: ignore[return-value]


def validate_test_dsn(dsn: str) -> None:
    """Refuse integration-test connections outside a loopback *_test database."""
    try:
        parsed = urlsplit(dsn)
    except ValueError as exc:
        raise ScaleConfigurationError("The PostgreSQL test DSN is invalid.") from exc
    database = parsed.path.removeprefix("/")
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ScaleConfigurationError("The PostgreSQL test DSN must use PostgreSQL.")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ScaleConfigurationError("The PostgreSQL test DSN must use a loopback host.")
    if not database.endswith("_test"):
        raise ScaleConfigurationError("The PostgreSQL test database must end in _test.")
