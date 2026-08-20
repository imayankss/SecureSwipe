# Deployment runbook and current status

## Current status

- Frontend: the static Next.js portfolio dashboard is deployed on Vercel at
  `https://secure-swipe.vercel.app`. The Vercel project root is `web/`; it
  deploys no FastAPI service, model bundle, raw data, or environment file.
- Backend: no public deployment is authorized or verified.
- Model storage: no external store is selected; bundles remain ignored local
  artifacts mounted read-only for container testing.
- Monitoring: deterministic offline reports and local metrics/logs exist; no
  hosted telemetry provider is selected.

Do not describe this state as a production deployment. Pushes, pull requests,
releases, public deployments, DNS changes, and paid resources require explicit
owner confirmation immediately before the action.

## Static frontend deployment record

- Provider: Vercel (local CLI deployment; no GitHub connection or push).
- Public URL: `https://secure-swipe.vercel.app`
- Deployed: 2026-08-20 (Asia/Kolkata).
- Exact deployed frontend source commit:
  `943d021c4757ac4102615eb26ceca0cf476baa76` (`Configure standalone Vercel
  frontend build`). This commit configures Vercel to run `next build` because
  the deployable `web/` directory intentionally does not include the parent
  Python exporter; the local release gate still runs `npm run data:check`.
- Environment variables: none. In particular,
  `NEXT_PUBLIC_SECURESWIPE_API_URL` is unset, so the optional synthetic API
  check has no configured origin and the static fallback remains active.
- Verification results:
  - Node 22.13.1: `npm test` passed (7 tests), `npm run build` passed (two
    statically prerendered routes), and `npm audit --audit-level=high` reported
    0 vulnerabilities.
  - `curl -sS -D - -o /dev/null https://secure-swipe.vercel.app/` returned
    HTTP 200 with `connect-src 'self'`, `X-Frame-Options: DENY`,
    `X-Content-Type-Options: nosniff`, and the stated referrer and permissions
    policies.
  - Browser verification found the visible locked-historical,
    already-observed-random-holdout, portfolio/educational, and non-production
    limitations. No backend request occurs by default; the static fallback is
    visible until an API check is explicitly requested.
  - The deployed HTML and JavaScript were checked for the local Vercel OIDC
    credential marker, Kaggle credential filename, private-key marker, and
    common live-key prefixes; none was present. The bundled client code retains
    the optional API feature name and `/v1/predict` implementation, but no API
    origin or credential is configured.
- No backend, API, model artifact, raw transaction data, Kaggle data, or
  credential is publicly deployed.

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
