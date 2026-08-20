# Container runbook

The image packages the reference FastAPI service only. It contains no dataset,
model bundle, notebook, report, frontend, test, or credential. A verified bundle
is mounted read-only at runtime. The API is not a payment authorization system
and the synthetic smoke bundle must never be presented as a trained fraud model.

## Build for Apple Silicon

From the repository root with Docker Desktop running:

```bash
SECURESWIPE_VCS_REF="$(git rev-parse HEAD)"
docker buildx build \
  --platform linux/arm64 \
  --build-arg VCS_REF="$SECURESWIPE_VCS_REF" \
  --load \
  --tag secureswipe-api:local \
  .
```

The image uses the reviewed multi-architecture digest for Python 3.12.13 on
Debian Trixie, applies explicitly versioned Debian security upgrades, installs
the hash-locked API closure in a separate dependency stage, and runs as UID/GID
10001. A single
Uvicorn worker avoids duplicating the in-memory model. Scale and concurrency
claims require measurement; none are implied by this configuration.

The final runtime removes pip after copying the locked dependency prefix because
serving never installs packages. The build stage retains its installer only long
enough to resolve the hash-locked API closure; it is not copied into the final
image.

## Generate the synthetic smoke bundle

```bash
.venv/bin/python scripts/create_synthetic_bundle.py \
  --output artifacts/synthetic-smoke
```

The command refuses to overwrite a non-empty directory. The bundle contains
only deterministic generated features and a small logistic-regression fixture.

## Run with restricted privileges

```bash
docker run --detach \
  --name secureswipe-api-smoke \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --publish 127.0.0.1:8000:8000 \
  --volume "$PWD/artifacts/synthetic-smoke:/artifacts/synthetic-smoke:ro" \
  --env SECURESWIPE_BUNDLE_MANIFEST=/artifacts/synthetic-smoke/manifest.json \
  secureswipe-api:local
```

Verify liveness, readiness, and one generated prediction:

```bash
curl --fail-with-body http://127.0.0.1:8000/health/live
curl --fail-with-body http://127.0.0.1:8000/health/ready
curl --fail-with-body http://127.0.0.1:8000/v1/predict \
  --header 'Content-Type: application/json' \
  --data @artifacts/synthetic-smoke/smoke_request.json
```

Remove the smoke container when finished:

```bash
docker stop secureswipe-api-smoke
docker rm secureswipe-api-smoke
```

These two commands affect only the explicitly named disposable container.

## Vulnerability scan and SBOM

```bash
docker run --rm \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  --volume "$PWD/.trivyignore.yaml:/.trivyignore.yaml:ro" \
  aquasec/trivy:0.70.0 image \
  --severity HIGH,CRITICAL \
  --exit-code 1 \
  --ignorefile /.trivyignore.yaml \
  secureswipe-api:local
docker sbom secureswipe-api:local \
  --format spdx-json \
  --output artifacts/secureswipe-api.spdx.json
```

The SBOM is a generated local artifact and is not a substitute for the source
dependency locks. Durable final evidence must retain the complete unfiltered scan
JSON, SPDX JSON, scanner/database metadata, image ID, OCI revision label, Git SHA,
both evidence-file checksums, and every exception disposition. Do not call this
gate passed until those records verify against the same final image.

The checked-in `.trivyignore.yaml` is not a blanket `ignore-unfixed` policy. It
lists only residual Debian findings that had no fix on 2026-08-20, records why
the affected tool/library is outside this restricted service's input and
execution paths, and expires every exception on 2026-09-20. CI still fails for
any unlisted high/critical finding. Rebuild on a newer base or remove an
exception as soon as Debian publishes a fix; never extend an expiry without a
new scan and review.

## Artifact replacement and rollback

The container is model-agnostic. To replace or roll back a model, stop the
current container and start the same immutable image with a different reviewed,
read-only bundle directory and manifest path. Readiness must pass before traffic
is moved. Never modify a mounted bundle in place, and retain its manifest and
hashes with the evaluation/run manifest that approved it.
