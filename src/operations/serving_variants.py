"""Benchmark-only serving variants for the MT4 concurrency experiment.

Nothing here is wired into normal service startup. The default application
behaviour is unchanged: ``api.service.ModelService`` still holds its global
inference lock, and the lock-free variant exists only so the experiment can
measure the lock's cost without editing the shipped class.

A variant is adopted as the default only if the MT4 protocol's lock-removal
decision rule is satisfied, which is a separate, explicit decision.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from typing import Literal

from api.service import ModelService

Variant = Literal["baseline", "lock_free"]

#: Environment variable the benchmark app factory reads.
VARIANT_ENV = "MT4_SERVING_VARIANT"


class _NullLock:
    """A context manager that acquires nothing.

    Used only to measure what the global inference lock costs. Substituting it
    is safe solely because the MT4 protocol requires concurrent semantic parity,
    audit validity, and idempotency to be proven first.
    """

    def __enter__(self) -> "_NullLock":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        return False


class LockFreeModelService(ModelService):
    """``ModelService`` with the global inference lock replaced by a no-op."""

    def __init__(self, bundle: object | None = None) -> None:
        super().__init__(bundle)  # type: ignore[arg-type]
        self._prediction_lock = _NullLock()  # type: ignore[assignment]


def build_service(bundle: object, variant: Variant) -> ModelService:
    """Return the service for a named benchmark variant."""
    if variant == "baseline":
        return ModelService(bundle)  # type: ignore[arg-type]
    if variant == "lock_free":
        return LockFreeModelService(bundle)
    raise ValueError(f"Unknown serving variant: {variant!r}")


def create_benchmark_app() -> object:
    """Uvicorn factory for the MT4 benchmark. Not used by normal startup."""
    from api.main import ApiSettings, create_app
    from src.artifacts.bundle import load_model_bundle

    variant: Variant = os.getenv(VARIANT_ENV, "baseline")  # type: ignore[assignment]
    settings = ApiSettings.from_environment()
    if settings.bundle_manifest is None:
        raise RuntimeError("SECURESWIPE_BUNDLE_MANIFEST must be set for the benchmark app.")
    bundle = load_model_bundle(
        Path(settings.bundle_manifest), trusted_root=Path(settings.artifact_root)
    )
    return create_app(service=build_service(bundle, variant), settings=settings)
