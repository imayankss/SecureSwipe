# Deployment runbook and current status

## Current status

- Frontend: a static Next.js deployment configuration exists under `web/`; no
  live URL is recorded or independently verified in this repository.
- Backend: no public deployment is authorized or verified.
- Model storage: no external store is selected; bundles remain ignored local
  artifacts mounted read-only for container testing.
- Monitoring: deterministic offline reports and local metrics/logs exist; no
  hosted telemetry provider is selected.

Do not describe this state as a production deployment. Pushes, pull requests,
releases, public deployments, DNS changes, and paid resources require explicit
owner confirmation immediately before the action.

## Local release-candidate gates

1. Run the clean data-free quality sequence in
   [REPRODUCIBILITY.md](REPRODUCIBILITY.md).
2. With Docker Desktop running, build `linux/arm64`, mount the deterministic
   synthetic bundle, and pass liveness/readiness/inference using
   [CONTAINER.md](CONTAINER.md).
3. Run the high/critical image scan and write the SPDX SBOM. Record image digest,
   scanner version/database time, and any reviewed exception.
4. Repeat the full quality gate twice without code changes.
5. For any real candidate model, require development/forward evidence, exact
   evaluation/service parity, bundle verification, monitoring reference data,
   and a named rollback bundle. The historical test is not a decision input.

The optional frontend live-demo mode is gated on steps 1–3. When implemented, it
must use synthetic examples, timeouts and explicit loading/error/unavailable
states, preserve static content, and expose no browser secret.

## Provider evaluation gate

Only after the local gates pass should the owner compare providers for:

| Need | Required evidence before selection |
|---|---|
| Static frontend | Build/runtime compatibility, preview isolation, headers, rollback, free-tier/usage limits |
| API container | `linux/arm64`/provider architecture support, cold start, memory/CPU, health routing, TLS, authentication/rate limiting, log controls |
| Model artifacts | Private immutable versioning, checksum retention, read-only delivery, access audit, rollback, size/egress cost |
| Monitoring | Redaction, retention, bounded labels, alert ownership, free-tier limits, export/deletion behavior |

Record current pricing, sleep/cold-start behavior, limits, region, secret names,
and estimated use at decision time. Those facts are time-sensitive and must be
verified from provider documentation; they are intentionally not guessed here.

## Candidate rollout

1. Build an immutable image and identify it by digest.
2. Select a reviewed immutable bundle manifest; never mutate a mounted bundle.
3. Start a candidate instance outside traffic with read-only filesystem,
   capability drop, no-new-privileges, bounded resources, and server-only config.
4. Verify bundle/model-info, liveness, readiness, one golden synthetic request,
   OpenAPI, metrics/log redaction, and bounded smoke load.
5. Move traffic through provider routing only after the prior instance remains
   available for rollback.
6. Observe errors/latency/readiness and score-distribution diagnostics. A drift
   signal opens investigation; it does not automatically change the model.

## Rollback

Route away from the candidate, then restart the last reviewed image digest with
the last reviewed bundle manifest. Re-run bundle verification, liveness,
readiness, model-info, golden synthetic inference, and bounded load before
restoring traffic. Preserve redacted incident evidence; never delete history or
edit a bundle in place. Provider-specific traffic and DNS steps must be added
after a provider is selected and rehearsed.
