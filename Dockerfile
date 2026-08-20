ARG PYTHON_IMAGE=python:3.12.13-slim-trixie@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

FROM ${PYTHON_IMAGE} AS dependencies

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements/api-linux.lock requirements/api-linux.lock
RUN python -m pip install \
    --require-hashes \
    --prefix=/install \
    --no-compile \
    -r requirements/api-linux.lock

FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="SecureSwipe fraud-risk reference API" \
      org.opencontainers.image.description="Portfolio reference service; not a payment authorization system" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SECURESWIPE_ARTIFACT_ROOT=/artifacts \
    SECURESWIPE_MAX_REQUEST_BYTES=65536

# Apply the reviewed Debian fixes published after the immutable upstream Python
# image was assembled. Explicit versions prevent a future repository update
# from silently changing this layer; the final image digest is the deployable
# identity.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        bsdutils=1:2.41.5-0+deb13u1 \
        libblkid1=2.41.5-0+deb13u1 \
        liblastlog2-2=2.41.5-0+deb13u1 \
        libmount1=2.41.5-0+deb13u1 \
        libsmartcols1=2.41.5-0+deb13u1 \
        libuuid1=2.41.5-0+deb13u1 \
        login=1:4.16.0-2+really2.41.5-0+deb13u1 \
        mount=2.41.5-0+deb13u1 \
        util-linux=2.41.5-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

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
