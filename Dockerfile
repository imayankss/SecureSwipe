ARG PYTHON_IMAGE=python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db

FROM ${PYTHON_IMAGE} AS dependencies

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements/api.lock requirements/api.lock
RUN python -m pip install \
    --require-hashes \
    --prefix=/install \
    --no-compile \
    -r requirements/api.lock

FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="SecureSwipe fraud-risk reference API" \
      org.opencontainers.image.description="Portfolio reference service; not a payment authorization system" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SECURESWIPE_ARTIFACT_ROOT=/artifacts \
    SECURESWIPE_MAX_REQUEST_BYTES=65536

RUN groupadd --gid 10001 secureswipe \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin secureswipe \
    && mkdir --mode=0755 /app /artifacts \
    && chown 10001:10001 /artifacts

COPY --from=dependencies /install /usr/local
WORKDIR /app
COPY --chown=10001:10001 api ./api
COPY --chown=10001:10001 src/__init__.py ./src/__init__.py
COPY --chown=10001:10001 src/artifacts ./src/artifacts
COPY --chown=10001:10001 src/inference ./src/inference
COPY --chown=10001:10001 src/preprocessing ./src/preprocessing

# Serving never installs packages; omit the base image's packaging installer and
# its avoidable runtime attack/vulnerability surface.
RUN python -m pip uninstall --yes pip

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).read()"]

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
