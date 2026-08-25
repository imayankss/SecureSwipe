"""SecureSwipe FastAPI reference service with fail-closed model readiness."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.audit import (
    AuditDecision,
    AuditIntegrityError,
    AuditLog,
    IdempotencyConflictError,
    IdempotencyRegistry,
    sha256_canonical,
)
from api.metrics import ApiMetrics
from api.schemas import (
    API_SCHEMA_VERSION,
    BatchPredictionRequest,
    BatchPredictionResponse,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    ModelInfoResponse,
    PredictionResponse,
    TransactionFeatures,
)
from api.service import ModelService, ModelUnavailableError, PredictionIntegrityError
from src.artifacts.bundle import ArtifactVerificationError, load_model_bundle

LOGGER = logging.getLogger("secureswipe.api")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
KNOWN_ROUTES = {
    "/health/live",
    "/health/ready",
    "/v1/model-info",
    "/v1/predict",
    "/v1/predict/batch",
    "/metrics",
}
ERROR_RESPONSE: dict[str, Any] = {"model": ErrorResponse}
INFERENCE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: ERROR_RESPONSE,
    413: ERROR_RESPONSE,
    422: ERROR_RESPONSE,
    500: ERROR_RESPONSE,
    503: ERROR_RESPONSE,
    504: ERROR_RESPONSE,
}


class PredictionTimeoutError(Exception):
    """Raised when synchronous inference exceeds the configured deadline."""


class CapacityExceededError(Exception):
    """Raised when in-flight prediction work exceeds the configured admission limit."""


class AuditUnavailableError(Exception):
    """Raised when required audit evidence cannot be recorded safely."""


class ConcurrencyGate:
    """Bounded, non-blocking admission control for synchronous inference work.

    Deliberately dependency-free: a thread-safe counter guarded by a lock,
    checked once per request with no queueing. When the limit is reached the
    caller fails closed immediately (503) instead of piling up work behind
    the single-writer model lock in ModelService.
    """

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        self._limit = limit
        self._in_flight = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self._in_flight >= self._limit:
                return False
            self._in_flight += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight


async def _run_admitted_inference(
    operation: Callable[..., Any],
    *args: Any,
    gate: ConcurrencyGate,
    timeout_seconds: float,
) -> Any:
    """Run one admitted worker without releasing its slot on client timeout.

    The worker task is shielded from request timeout/cancellation. Its done
    callback owns the admission slot and releases it only after the underlying
    threadpool operation has actually finished.
    """
    if not gate.try_acquire():
        raise CapacityExceededError(f"Prediction capacity exceeded ({gate.in_flight} in flight).")

    try:
        worker_task = asyncio.create_task(run_in_threadpool(operation, *args))
    except BaseException:
        gate.release()
        raise

    def release_when_worker_finishes(completed: asyncio.Task[Any]) -> None:
        try:
            completed.exception()
        except asyncio.CancelledError:
            pass
        finally:
            gate.release()

    worker_task.add_done_callback(release_when_worker_finishes)
    return await _run_bounded(
        asyncio.shield(worker_task),
        timeout_seconds=timeout_seconds,
    )


async def _run_bounded(awaitable: Awaitable[Any], *, timeout_seconds: float) -> Any:
    """Await coro with a hard deadline, converting timeout into a stable error.

    Note: cancelling the awaited coroutine does not forcibly stop the
    underlying threadpool worker (CPython threads cannot be killed). The
    caller reliably gets a timely error and the connection is not held open;
    the worker thread still finishes in the background and releases the
    model lock when it does. This bounds client-facing latency, not raw
    server-side compute -- documented as a known limitation, not hidden.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise PredictionTimeoutError(
            f"Prediction exceeded the {timeout_seconds}s deadline."
        ) from exc


def configure_api_logging() -> None:
    """Ensure request JSON reaches stderr even with Uvicorn access logs disabled."""
    LOGGER.setLevel(logging.INFO)
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.propagate = False


@dataclass(frozen=True)
class ApiSettings:
    artifact_root: Path
    bundle_manifest: Path | None
    cors_origins: tuple[str, ...]
    max_request_bytes: int = 65_536
    prediction_timeout_seconds: float = 5.0
    max_concurrent_predictions: int = 16
    audit_log_path: Path | None = None

    def __post_init__(self) -> None:
        if "*" in self.cors_origins:
            raise ValueError("CORS origins must not contain wildcard '*'.")
        if not 1_024 <= self.max_request_bytes <= 1_048_576:
            raise ValueError("max_request_bytes must be between 1024 and 1048576.")
        if not 0.1 <= self.prediction_timeout_seconds <= 30.0:
            raise ValueError("prediction_timeout_seconds must be between 0.1 and 30.0.")
        if not 1 <= self.max_concurrent_predictions <= 256:
            raise ValueError("max_concurrent_predictions must be between 1 and 256.")

    @classmethod
    def from_environment(cls) -> "ApiSettings":
        root = Path(os.getenv("SECURESWIPE_ARTIFACT_ROOT", "artifacts")).expanduser()
        manifest_value = os.getenv("SECURESWIPE_BUNDLE_MANIFEST", "").strip()
        origins = tuple(
            item.strip()
            for item in os.getenv("SECURESWIPE_CORS_ORIGINS", "").split(",")
            if item.strip()
        )
        if "*" in origins:
            raise ValueError("SECURESWIPE_CORS_ORIGINS must not contain wildcard '*'.")
        max_bytes = int(os.getenv("SECURESWIPE_MAX_REQUEST_BYTES", "65536"))
        if not 1_024 <= max_bytes <= 1_048_576:
            raise ValueError("SECURESWIPE_MAX_REQUEST_BYTES must be between 1024 and 1048576.")
        timeout_seconds = float(os.getenv("SECURESWIPE_PREDICTION_TIMEOUT_SECONDS", "5.0"))
        if not 0.1 <= timeout_seconds <= 30.0:
            raise ValueError("SECURESWIPE_PREDICTION_TIMEOUT_SECONDS must be between 0.1 and 30.0.")
        max_concurrent = int(os.getenv("SECURESWIPE_MAX_CONCURRENT_PREDICTIONS", "16"))
        if not 1 <= max_concurrent <= 256:
            raise ValueError("SECURESWIPE_MAX_CONCURRENT_PREDICTIONS must be between 1 and 256.")
        audit_value = os.getenv("SECURESWIPE_AUDIT_LOG", "").strip()
        return cls(
            artifact_root=root,
            bundle_manifest=Path(manifest_value).expanduser() if manifest_value else None,
            cors_origins=origins,
            max_request_bytes=max_bytes,
            prediction_timeout_seconds=timeout_seconds,
            max_concurrent_predictions=max_concurrent,
            audit_log_path=Path(audit_value).expanduser() if audit_value else None,
        )


def _request_id_from_headers(headers: list[tuple[bytes, bytes]]) -> str:
    for key, value in headers:
        if key.lower() == b"x-request-id":
            candidate = value.decode("ascii", errors="ignore")
            if REQUEST_ID_PATTERN.fullmatch(candidate):
                return candidate
    return uuid.uuid4().hex


def _error_payload(request_id: str, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return ErrorResponse(
        schema_version=API_SCHEMA_VERSION,
        request_id=request_id,
        error=ErrorDetail(code=code, message=message, details=details),
    ).model_dump(mode="json")


class RequestBodyLimitMiddleware:
    """Bound POST request memory even when Content-Length is omitted."""

    def __init__(self, app: Callable[..., Any], max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        request_id = str(
            scope.get("state", {}).get("request_id")
            or _request_id_from_headers(scope.get("headers", []))
        )
        scope.setdefault("state", {})["request_id"] = request_id
        scope["headers"] = [
            (key, value)
            for key, value in scope.get("headers", [])
            if key.lower() != b"x-request-id"
        ] + [(b"x-request-id", request_id.encode("ascii"))]
        messages: list[dict[str, Any]] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    response = JSONResponse(
                        status_code=413,
                        content=_error_payload(
                            request_id,
                            "request_too_large",
                            f"Request body exceeds the {self.max_bytes}-byte limit.",
                        ),
                        headers={"X-Request-ID": request_id},
                    )
                    await response(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                return

        iterator = iter(messages)

        async def replay() -> dict[str, Any]:
            try:
                return next(iterator)
            except StopIteration:
                return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)


def _request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if existing:
        return str(existing)
    candidate = request.headers.get("x-request-id", "")
    request.state.request_id = (
        candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else uuid.uuid4().hex
    )
    return request.state.request_id


def create_app(
    *,
    service: ModelService | None = None,
    settings: ApiSettings | None = None,
) -> FastAPI:
    configure_api_logging()
    configured = settings or ApiSettings.from_environment()
    injected_service = service

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if injected_service is not None:
            application.state.model_service = injected_service
        elif configured.bundle_manifest is not None:
            try:
                bundle = load_model_bundle(
                    configured.bundle_manifest,
                    trusted_root=configured.artifact_root,
                )
            except (ArtifactVerificationError, FileNotFoundError, ValueError) as exc:
                raise RuntimeError(f"Configured model bundle failed verification: {exc}") from exc
            application.state.model_service = ModelService(bundle)
        else:
            application.state.model_service = ModelService()
        if configured.audit_log_path is not None:
            model_service: ModelService = application.state.model_service
            if model_service.ready and model_service.model_fingerprint_sha256 is None:
                raise RuntimeError(
                    "Audit evidence requires a verified model-artifact SHA-256 fingerprint."
                )
            application.state.audit_log = AuditLog(configured.audit_log_path)
        else:
            application.state.audit_log = None
        yield

    application = FastAPI(
        title="SecureSwipe Fraud-Risk Reference API",
        version=API_SCHEMA_VERSION,
        description=(
            "Portfolio-grade reference inference API. It is not a bank authorization "
            "system and must not process real customer transactions."
        ),
        lifespan=lifespan,
    )
    application.state.metrics = ApiMetrics()
    application.state.concurrency_gate = ConcurrencyGate(configured.max_concurrent_predictions)
    application.state.prediction_timeout_seconds = configured.prediction_timeout_seconds
    application.state.idempotency_registry = IdempotencyRegistry()
    application.add_middleware(RequestBodyLimitMiddleware, max_bytes=configured.max_request_bytes)
    if configured.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(configured.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )

    @application.middleware("http")
    async def request_context(request: Request, call_next: Callable[..., Any]) -> Any:
        request_id = _request_id(request)
        started = time.perf_counter()
        status = 500
        response = None
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            latency = time.perf_counter() - started
            application.state.metrics.observe_request(
                request.method, request.url.path, status, latency
            )
            model_service: ModelService | None = getattr(application.state, "model_service", None)
            LOGGER.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": (
                            request.method
                            if request.method in {"GET", "POST", "OPTIONS"}
                            else "OTHER"
                        ),
                        "route": (
                            request.url.path if request.url.path in KNOWN_ROUTES else "unmatched"
                        ),
                        "status": status,
                        "latency_ms": round(latency * 1000, 3),
                        "model_version": model_service.model_version if model_service else None,
                    },
                    separators=(",", ":"),
                )
            )
        if response is None:
            raise RuntimeError("Request failed before a response was created.")
        response.headers["X-Request-ID"] = request_id
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"type": item["type"], "location": list(item["loc"]), "message": "Invalid value."}
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                _request_id(request), "validation_error", "Request validation failed.", details
            ),
        )

    @application.exception_handler(ModelUnavailableError)
    async def unavailable_error(request: Request, exc: ModelUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=_error_payload(_request_id(request), "model_unavailable", str(exc)),
        )

    @application.exception_handler(PredictionIntegrityError)
    async def prediction_integrity_error(
        request: Request, exc: PredictionIntegrityError
    ) -> JSONResponse:
        LOGGER.error(
            json.dumps({"event": "prediction_integrity_error", "request_id": _request_id(request)})
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                _request_id(request),
                "prediction_integrity_error",
                "The configured model returned invalid output.",
            ),
        )

    @application.exception_handler(PredictionTimeoutError)
    async def prediction_timeout_error(
        request: Request, exc: PredictionTimeoutError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=504,
            content=_error_payload(_request_id(request), "prediction_timeout", str(exc)),
        )

    @application.exception_handler(CapacityExceededError)
    async def capacity_exceeded_error(request: Request, exc: CapacityExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=_error_payload(_request_id(request), "capacity_exceeded", str(exc)),
        )

    @application.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_error(
        request: Request, exc: IdempotencyConflictError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=_error_payload(_request_id(request), "idempotency_conflict", str(exc)),
        )

    @application.exception_handler(AuditUnavailableError)
    async def audit_unavailable_error(request: Request, exc: AuditUnavailableError) -> JSONResponse:
        LOGGER.error(
            json.dumps(
                {"event": "audit_unavailable", "request_id": _request_id(request)},
                separators=(",", ":"),
            )
        )
        return JSONResponse(
            status_code=503,
            content=_error_payload(_request_id(request), "audit_unavailable", str(exc)),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(_request_id(request), "http_error", str(exc.detail)),
            headers=exc.headers,
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.error(
            json.dumps(
                {
                    "event": "unhandled_error",
                    "request_id": _request_id(request),
                    "error_class": type(exc).__name__,
                },
                separators=(",", ":"),
            )
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                _request_id(request),
                "internal_error",
                "An internal error occurred.",
            ),
        )

    def current_service() -> ModelService:
        return application.state.model_service

    def input_digest(*, route: str, transactions: list[TransactionFeatures]) -> str:
        return sha256_canonical(
            {
                "api_schema_version": API_SCHEMA_VERSION,
                "route": route,
                "transactions": [transaction.canonical_values() for transaction in transactions],
            }
        )

    def append_audit_evidence(
        *,
        request_id: str,
        canonical_input_digest: str,
        latency_ms: float,
        results: list[Any],
    ) -> None:
        audit_log: AuditLog | None = application.state.audit_log
        if audit_log is None:
            return
        model_fingerprint = current_service().model_fingerprint_sha256
        if model_fingerprint is None:
            raise AuditUnavailableError(
                "Audit evidence is unavailable; no inference result was released."
            )
        try:
            audit_log.append_inference(
                request_id=request_id,
                api_schema_version=API_SCHEMA_VERSION,
                input_digest_sha256=canonical_input_digest,
                latency_ms=latency_ms,
                decisions=[
                    AuditDecision(
                        score=result.decision_score,
                        threshold=result.operating_threshold,
                        decision=result.decision,
                        model_version=result.model_version,
                        model_fingerprint_sha256=model_fingerprint,
                    )
                    for result in results
                ],
            )
        except (AuditIntegrityError, OSError) as exc:
            raise AuditUnavailableError(
                "Audit evidence is unavailable; no inference result was released."
            ) from exc

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def health_live() -> HealthResponse:
        return HealthResponse(status="live")

    @application.get(
        "/health/ready",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
        tags=["health"],
    )
    async def health_ready() -> HealthResponse | JSONResponse:
        model_service = current_service()
        health = HealthResponse(
            status="ready" if model_service.ready else "not_ready",
            model_version=model_service.model_version,
        )
        if not model_service.ready:
            return JSONResponse(status_code=503, content=health.model_dump(mode="json"))
        return health

    @application.get(
        "/v1/model-info",
        response_model=ModelInfoResponse,
        responses={500: ERROR_RESPONSE, 503: ERROR_RESPONSE},
        tags=["model"],
    )
    async def model_info() -> ModelInfoResponse:
        info = current_service().model_info()
        return ModelInfoResponse(
            model_version=info.model_version,
            bundle_format_version=info.bundle_format_version,
            score_type=info.score_type,
            calibrated=info.calibrated,
            operating_threshold=info.operating_threshold,
            feature_schema=list(info.feature_schema),
            training_data_fingerprint=info.training_data_fingerprint,
            evidence_category=info.evidence_category,
            historical_taint=info.historical_taint,
            decision_eligible=info.decision_eligible,
            historical_metrics_claimed=info.historical_metrics_claimed,
            evaluation_performed=info.evaluation_performed,
        )

    @application.post(
        "/v1/predict",
        response_model=PredictionResponse,
        responses=INFERENCE_ERROR_RESPONSES,
        tags=["inference"],
    )
    async def predict(
        transaction: TransactionFeatures, request: Request, response: Response
    ) -> PredictionResponse:
        request_id = _request_id(request)
        canonical_input_digest = input_digest(route="/v1/predict", transactions=[transaction])
        registry: IdempotencyRegistry = application.state.idempotency_registry
        reservation = await registry.reserve(
            request_id=request_id,
            input_digest_sha256=canonical_input_digest,
        )
        if not reservation.owner:
            response.headers["X-Idempotent-Replay"] = "true"
            return await registry.replay(reservation)

        started = time.perf_counter()
        try:
            gate: ConcurrencyGate = application.state.concurrency_gate
            result = await _run_admitted_inference(
                current_service().predict_one,
                transaction,
                gate=gate,
                timeout_seconds=application.state.prediction_timeout_seconds,
            )
            application.state.metrics.observe_scores([result.decision_score])
            prediction = PredictionResponse(request_id=request_id, **result.model_dump())
            append_audit_evidence(
                request_id=request_id,
                canonical_input_digest=canonical_input_digest,
                latency_ms=(time.perf_counter() - started) * 1000,
                results=[result],
            )
            registry.complete(reservation, prediction)
            return prediction
        except BaseException as exc:
            await registry.fail(reservation, exc)
            raise

    @application.post(
        "/v1/predict/batch",
        response_model=BatchPredictionResponse,
        responses=INFERENCE_ERROR_RESPONSES,
        tags=["inference"],
    )
    async def predict_batch(
        batch: BatchPredictionRequest, request: Request, response: Response
    ) -> BatchPredictionResponse:
        request_id = _request_id(request)
        canonical_input_digest = input_digest(
            route="/v1/predict/batch", transactions=batch.transactions
        )
        registry: IdempotencyRegistry = application.state.idempotency_registry
        reservation = await registry.reserve(
            request_id=request_id,
            input_digest_sha256=canonical_input_digest,
        )
        if not reservation.owner:
            response.headers["X-Idempotent-Replay"] = "true"
            return await registry.replay(reservation)

        started = time.perf_counter()
        try:
            gate: ConcurrencyGate = application.state.concurrency_gate
            results = await _run_admitted_inference(
                current_service().predict_many,
                batch.transactions,
                gate=gate,
                timeout_seconds=application.state.prediction_timeout_seconds,
            )
            application.state.metrics.observe_scores([result.decision_score for result in results])
            prediction = BatchPredictionResponse(
                request_id=request_id,
                model_version=results[0].model_version,
                count=len(results),
                predictions=results,
            )
            append_audit_evidence(
                request_id=request_id,
                canonical_input_digest=canonical_input_digest,
                latency_ms=(time.perf_counter() - started) * 1000,
                results=results,
            )
            registry.complete(reservation, prediction)
            return prediction
        except BaseException as exc:
            await registry.fail(reservation, exc)
            raise

    @application.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(
            application.state.metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return application


app = create_app()
