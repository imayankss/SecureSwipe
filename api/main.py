"""SecureSwipe FastAPI reference service with fail-closed model readiness."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

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


@dataclass(frozen=True)
class ApiSettings:
    artifact_root: Path
    bundle_manifest: Path | None
    cors_origins: tuple[str, ...]
    max_request_bytes: int = 65_536

    def __post_init__(self) -> None:
        if "*" in self.cors_origins:
            raise ValueError("CORS origins must not contain wildcard '*'.")
        if not 1_024 <= self.max_request_bytes <= 1_048_576:
            raise ValueError("max_request_bytes must be between 1024 and 1048576.")

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
        return cls(
            artifact_root=root,
            bundle_manifest=Path(manifest_value).expanduser() if manifest_value else None,
            cors_origins=origins,
            max_request_bytes=max_bytes,
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

        request_id = _request_id_from_headers(scope.get("headers", []))
        scope.setdefault("state", {})["request_id"] = request_id
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
                        "method": request.method,
                        "route": request.url.path,
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

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(_request_id(request), "http_error", str(exc.detail)),
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception(
            json.dumps(
                {"event": "unhandled_error", "request_id": _request_id(request)},
                separators=(",", ":"),
            ),
            exc_info=exc,
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

    @application.get("/v1/model-info", response_model=ModelInfoResponse, tags=["model"])
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
        )

    @application.post("/v1/predict", response_model=PredictionResponse, tags=["inference"])
    async def predict(transaction: TransactionFeatures, request: Request) -> PredictionResponse:
        result = current_service().predict_one(transaction)
        application.state.metrics.observe_scores([result.decision_score])
        return PredictionResponse(request_id=_request_id(request), **result.model_dump())

    @application.post(
        "/v1/predict/batch",
        response_model=BatchPredictionResponse,
        tags=["inference"],
    )
    async def predict_batch(
        batch: BatchPredictionRequest, request: Request
    ) -> BatchPredictionResponse:
        results = current_service().predict_many(batch.transactions)
        application.state.metrics.observe_scores([result.decision_score for result in results])
        return BatchPredictionResponse(
            request_id=_request_id(request),
            model_version=results[0].model_version,
            count=len(results),
            predictions=results,
        )

    @application.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(
            application.state.metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return application


app = create_app()
