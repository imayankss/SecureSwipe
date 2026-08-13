# Threat model

## Scope

This model covers the local/container FastAPI reference, versioned model bundle,
static dashboard export, CI workflows, and offline development tooling. It does
not claim coverage of a real payment network, identity provider, data warehouse,
review operation, or public production deployment.

## Assets and trust boundaries

| Asset | Boundary | Primary control |
|---|---|---|
| Model/preprocessor/calibrator | Server-controlled read-only artifact root | Manifest, schema/runtime/type/size/SHA-256 verification before deserialization |
| Synthetic or raw feature request | Untrusted HTTP client to API process | Strict finite named schema, unknown-field rejection, body/batch limits |
| Logs and metrics | API process to operator | No feature vectors; bounded labels; request IDs |
| Historical reports/figures | Tracked source to static web payload | Recomputed invariants, source digest, read-only byte comparison |
| Source and dependency graph | Pull request to CI runner/image | Read-only permissions, hash locks, immutable action revisions, scans |
| Kaggle/raw data/credentials | Local secret/data store to offline pipeline | Ignore/context exclusions; never required by fixture CI |

## Principal threats and mitigations

- **Malicious pickle execution:** model paths never come from requests. Every
  payload passes trusted-root containment, manifest, all-payload checksum, type,
  schema, Python, and dependency checks before any load. Residual risk remains if
  a trusted producer or artifact store is compromised; checksums are not signatures.
- **Training-serving skew:** one bundle contains preprocessing, model, optional
  calibrator, threshold, ordered schema, and provenance. Golden direct/API parity
  tests cover the serving path.
- **Resource exhaustion:** request bytes and batch rows are capped; numerical
  values are bounded and one worker avoids accidental model duplication. There is
  no authentication/rate limiter because no public deployment is authorized.
- **Data/error disclosure:** stable errors omit input values; structured logs do
  not include transaction vectors; CORS is an explicit allowlist with no wildcard.
- **Metric/report tampering:** confusion and derived metrics, selected threshold,
  class totals, and public figure bytes are cross-checked. Verification never
  repairs files as a side effect.
- **Dependency/workflow compromise:** Python installs use hashes, npm uses its
  lock, base image/actions use immutable digests/revisions, permissions are
  minimal, and CI scans dependencies, code, secrets, and images.
- **Model abuse/overclaim:** API/dashboard documentation identifies the system as
  a portfolio reference. Raw scores are not probabilities; review/pass is not an
  authorization decision; the historical test is quarantined.

## OWASP API-oriented review

Object-level authorization and function authorization are not applicable to the
current anonymous, stateless synthetic demo because it exposes no user-owned
objects or administrative functions. If a public demo is approved, authentication,
rate limiting, abuse controls, TLS termination, proxy/body limits, and operator
access must be designed and tested before exposure. SSRF/file upload paths are
absent. Inventory is the versioned `/v1` OpenAPI contract; `/metrics` should be
network-restricted by the deployment layer.

## Residual risks and required response

No artifact signature/transparency log, external rate limiter, WAF, authentication,
distributed tracing, or real incident channel exists. Docker/image scans remain
blocked locally until Docker Desktop runs; CI definitions are not evidence until
they execute on GitHub. Suspected artifact compromise requires stopping readiness,
removing traffic, preserving hashes/logs, replacing with a previously reviewed
bundle, and rotating any affected storage credentials.
