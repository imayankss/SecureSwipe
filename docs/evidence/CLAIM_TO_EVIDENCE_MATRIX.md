# SecureSwipe claim-to-evidence matrix

Every claim that may be spoken in the pitch or written in the submission form
must appear in this table and must map to a committed artifact, a named test, or
a measured report. A claim that is not in this table has not been cleared to be
made.

- **Released content:** `main` at `399a482`, tree
  `41bdc41710234fb4edef1edccf167513a665aa55`. Application code, frontend, and
  workflows are unchanged from the CI-green tree `6e112b8b…` (`374e167`, PR
  head `4c712c7`); the delta is confined to these evidence documents.
- **Status of this document:** the evidence below is committed, locally
  verified, and confirmed by CI. The release is **frozen** — see "Release
  freeze status" at the end.

## 1 — Positioning and scope

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 1.1 | Built for Razorpay AI Builder Internship Track 2 (AI Risk Manager); the loss class is payment-card fraud on an extremely imbalanced dataset. | `README.md`; dashboard hero | Rendered and read at desktop 1280×800 and mobile 375×812 in this session |
| 1.2 | Defense-only: a fraud-risk signal and human-review decision aid. It never performs autonomous payment authorization, capture, or blocking. | `README.md`; `docs/LIMITATIONS.md`; dashboard badges "No autonomous payment blocking", "human review remains explicit" | Decision values are bounded in code to `human_review` / `below_review_threshold` / unavailable; the authorization-like value `pass` was removed from detector responses (ledger, Micro-task 3) |
| 1.3 | Every decision surface resolves to exactly three bounded outcomes and never to an approve/block action. | `api/service.py`, `api/schemas.py` | `tests/test_api.py` prediction and failure-path tests; observed live in container smoke, which returned `below_review_threshold` |
| 1.4 | Four evidence categories are kept separate and are labeled on every panel: historical evaluation, genuine demo inference, synthetic plumbing test, illustrative cost scenario. | `README.md`; `web/components/dashboard/EvidenceLegend.tsx`; `web/components/EvidenceLabel.tsx` | Legend rendered and visually confirmed at both viewports this session |

## 2 — Locked historical evaluation

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 2.1 | One locked held-out test run reports threshold `0.53`, TP/FP/FN/TN `62 / 27 / 12 / 42,621`, precision `69.66%`, recall `83.78%`, PR-AUC `0.8288`, ROC-AUC `0.9613`. | `reports/final/final_model_evaluation.json` | Values read directly from the locked artifact in this session; all match the expected locked figures exactly |
| 2.2 | The locked result is tamper-evident and is verified before use. | `reports/final/historical_observation.lock.json`; `scripts/verify_historical_observation.py` | Script run on the exact candidate in a clean worktree: `status=locked_historical_observation_verified`, 3 files verified. Backed by `test_historical_verifier_detects_tamper_before_use`, `test_fabricated_or_tampered_scores_are_rejected`, `test_threshold_tamper_fails_metric_cross_check` |
| 2.3 | Holdout scale: 42,722 rows, 74 fraud cases. | `web/public/data/dashboard.json`; dashboard cards | Rendered this session; export verified byte-deterministic by `scripts/export_web_data.py --check` |
| 2.4 | These historical numbers never change and are never recomputed in the browser. | Static export pipeline | `scripts/export_web_data.py --check` passed on the candidate; `tests/test_export_web_data.py` |

**Must not be claimed:** that the locked metrics were produced by the bundle
currently served. That linkage is explicitly unproven — see 3.3.

## 3 — Genuine model inference and provenance

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 3.1 | A real XGBoost estimator executes through the FastAPI service; inference is genuine, not mocked. | `artifacts/historical-reference-demo-v1/manifest.json` (local, intentionally gitignored); `api/`, `src/artifacts/bundle.py` | Manifest SHA-256 `e355834d…`, model `5ce63f1a…`, preprocessor `07d4a9f4…`; loader plus golden runtime probe accept a real `xgboost.sklearn.XGBClassifier` (ledger, Micro-tasks 1–3) |
| 3.2 | Direct-model, single-API, and batch-API outputs agree within a declared tolerance of absolute `1e-12`. | `tests/test_api.py` parity tests | Ledger, Micro-task 3 |
| 3.3 | The served bundle is historical-tainted, **not** decision-eligible, and **not** proven to be the model that produced the locked metrics. | Manifest flags `historical_taint=true`, `decision_eligible=false`, `historical_metrics_claimed=false`, `evaluation_performed=false`; surfaced in the API `provenance` block | Observed directly in container smoke response this session |
| 3.4 | Responses carry request ID, model/bundle version, schema version, model score, threshold, bounded decision, and provenance. | `api/schemas.py` | Live container response this session contained every field |
| 3.5 | The score is a model score, not a calibrated fraud probability. | `score_type: "raw_score"`, `calibrated_probability: null` | Observed in the live response; asserted by the container smoke assertion script |

**Must not be claimed:** authenticated original source inputs, reproduced
training data, or calibration. The four source Parquet inputs were not found;
`candidate_identity_status=pending_independent_verification` stands.

## 4 — Fail-closed, audit, and idempotency

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 4.1 | A missing or corrupt bundle never yields a silent approval: readiness fails and inference returns an explicit unavailable result. | `test_unavailable_model_is_live_but_not_ready`, `test_configured_corrupt_bundle_refuses_startup`, `test_manifest_tampering_fails_closed` | Full suite green on the candidate (758 passed) |
| 4.2 | Scoring timeout returns HTTP 504 `prediction_timeout`; capacity saturation returns HTTP 503 `capacity_exceeded`; audit-sink failure returns HTTP 503 `audit_unavailable`. No case yields a decision. | `test_prediction_exceeding_deadline_returns_stable_timeout_error`, `test_prediction_capacity_exceeded_fails_closed_deterministically`, `test_transient_audit_sink_failure_fails_closed_then_recovers_without_sleeping` | Deterministic `threading.Event`/`Condition` synchronization — no sleep-based tests |
| 4.3 | Audit evidence is **tamper-evident append-only**, not immutable storage. | `api/audit.py`; `scripts/verify_api_audit_log.py` | `test_canonical_chain_contains_only_bounded_redacted_evidence`, `test_verifier_detects_mutation_deletion_and_reordering`, `test_writer_refuses_to_append_after_external_tampering` |
| 4.4 | Duplicate requests replay the original result without rescoring or creating a duplicate audit event. | `test_duplicate_prediction_replays_without_rescoring_or_duplicate_audit_event` | Ledger, Micro-task 7–8 |
| 4.5 | PAN, CVV, secrets, and raw feature vectors are absent from logs and audit events. | Redaction tests incl. `test_invalid_values_use_stable_redacted_error_contract`, `test_api_info_logging_is_enabled_and_emits_parseable_redacted_json`, `test_contract_audit_reports_violation_without_row_values` | Full suite green |
| 4.6 | One failure and recovery can be demonstrated in under 20 seconds. | `scripts/demo_api_failure_recovery.py` | Measured `0.242 s` against a 20 s ceiling (ledger, Micro-task 8) |

**Must not be claimed:** immutable/WORM storage, distributed audit or
idempotency, crash recovery, multi-replica ordering, or authentication. Replay
state is in-process and lost on restart.

## 5 — Measured performance and efficiency

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 5.1 | A fixed-input loopback run recorded 500/500 valid responses at concurrency 8 with 0 errors, 0 timeouts, 0 non-2xx: p50 44.63 ms, p95 80.37 ms, p99 308.48 ms, 169.35 successful req/s. | `reports/operations/2026-08-25_genuine_model_api_benchmark.md` and `.json` (SHA-256 `f4c9023e…`) | One macOS 26.5.2 / arm64 Apple M2 Uvicorn worker; harness `scripts/run_local_load_test.py`; evidence contract asserted by `tests/test_load_test.py` |
| 5.2 | Core model inference consumes **zero LLM tokens**. | `core_model_inference_llm_tokens: 0` in the benchmark JSON | Deterministic tabular XGBoost path; no LLM in the inference path |
| 5.3 | Cold start measured 5.85 s as an end-to-end **upper bound** including readiness polling and client startup. | Same report | Explicitly labeled an upper bound, not server-internal telemetry |
| 5.4 | The earlier logistic-regression run is synthetic serving-path plumbing evidence only. | `reports/operations/2026-08-24_local_single_node_serving_benchmark.md` | Labeled as such in README and ledger; never combined with 5.1 |

**Must not be claimed:** 1,000 or 10,000 RPS, production capacity, an SLO,
public-network or multi-node results, or representative traffic. The p99 of
308.48 ms is disclosed rather than hidden. This measurement was taken on a dirty
worktree before the release commit and is not a release-SHA measurement.

## 6 — Illustrative cost scenario

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 6.1 | The panel is a what-if calculator over the locked confusion-matrix counts with user-editable INR assumptions (review cost, legitimate-customer friction, missed-fraud loss, chargeback handling). | `web/components/IllustrativeCostScenario.tsx` | `web/__tests__/illustrative-cost-scenario.test.tsx`; `tests/test_cost_analysis.py` (8 tests incl. zero-cost, high-FP, high-FN, boundary) |
| 6.2 | The exact disclaimer "Illustrative scenario — not Razorpay economics and not a production-optimal threshold." is visibly displayed. | Dashboard | Visually confirmed this session at both 1280×800 and 375×812 |

**Must not be claimed:** real savings, Razorpay economics, ROI, or a
production-optimal threshold.

## 7 — Engineering and security posture

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 7.1 | The full Python suite passes on the exact candidate in a clean checkout: **758 passed**. | `pytest` | Run in a clean detached worktree containing neither the gitignored bundle nor unrelated untracked files |
| 7.2 | Lint, types, and compile are clean: ruff, `compileall`, and both CI mypy invocations (30 critical source files + the isolated reference-stage wrapper). | CI-equivalent commands | Run on the exact candidate this session |
| 7.3 | Frontend passes on the CI-pinned Node 22.13.1: eslint, `tsc --noEmit`, 23 vitest tests, production build, 5 Playwright/Chromium e2e tests. | `web/` | e2e covers keyboard reachability, a WCAG scan, mobile navigation, desktop + 375px overflow/broken-link/console-error checks, and one genuine live-inference validation |
| 7.4 | No secrets are present anywhere in full Git history. | TruffleHog 3.96.0 (CI-pinned), `--exclude-detectors=Lob` | 2,348 chunks / 4,860,758 bytes: **0 verified and 0 unverified secrets** |
| 7.5 | Dependencies are hash-locked and free of known vulnerabilities. | `requirements/*.lock`, `web/package-lock.json` | `pip_audit` on both Linux locks — none known; `npm audit --audit-level=high` — 0 |
| 7.6 | The container runs hardened: non-root uid 10001, no pip, read-only rootfs, all capabilities dropped, `no-new-privileges`. | `Dockerfile` | Verified in-container this session; `tests/test_container_contract.py` |
| 7.7 | The candidate image has no HIGH or CRITICAL vulnerabilities. | Trivy 0.70.0 with repo `.trivyignore.yaml` | **Exit 0, 0 HIGH/CRITICAL** on `linux/arm64` image `sha256:e894e688…`, whose `org.opencontainers.image.revision` label equals the candidate SHA |
| 7.8 | No raw data, model weights, or credentials are committed. | Candidate tree inspection | No `.joblib`/`.pkl`/`.parquet` payloads committed; only aggregate report CSVs. `web/.env.local` is untracked and gitignored |
| 7.9 | The container release target is `linux/amd64`, which CI builds, smoke-tests, scans, and produces an SBOM for. | `.github/workflows/container.yml`; `docs/CONTAINER.md` | The `Container` workflow matrix is `linux/amd64` only |

**Scope note:** row 7.7's local Trivy run covers `linux/arm64`, the architecture
of the verification host; CI scans `linux/amd64`. **No arm64 container support
is claimed** — the emulated `linux/arm64` CI leg is deferred because the
container never completes startup under QEMU on GitHub-hosted runners. That was
reproduced three times, did not reproduce locally on native arm64 or
Rosetta-emulated amd64, and was not root caused. Do not state or imply arm64
container support anywhere in the pitch or the form.

## 8 — Deployment status

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 8.1 | There is **no** verified public deployment of this release candidate, and any prior static URL is not evidence for it. | `README.md` "Live Demo" | Checked-in workflows perform no deployment |
| 8.2 | The static dashboard remains useful with the local API down. | Dashboard | Rendered this session with **no API running**: locked historical evidence displayed, zero console errors, no page-level horizontal overflow at 375px |
| 8.3 | A model/bundle rollback path is documented and gated on explicit owner approval. | `docs/OPERATIONS.md:203` | Read this session |

**Must not be claimed:** a live URL, uptime, or production traffic, unless and
until a deployment is actually performed and verified.

## Release freeze status

**FROZEN.** All three workflows are green on `main` at merge commit
`374e167`, whose tree `6e112b8babac3de06a63226e86eda3658fb7e54b` is identical
to the verified PR head `4c712c7`, so CI validated exactly this content.

| Workflow | Conclusion | Covers |
| --- | --- | --- |
| Quality | success | Python suite, ruff, both mypy targets, deterministic export/historical/monitoring verifiers, hash-locked Linux install, wheel build and inventory, pip-audit; frontend lint/typecheck/vitest/build/Playwright and npm audit |
| Security | success | TruffleHog over full history; CodeQL for `python` and `javascript-typescript` |
| Container | success | `linux/amd64` build, smoke, Trivy HIGH/CRITICAL scan, SPDX SBOM |

No new feature may be added on top of this commit. A claim of "CI green" is
now supported, stated as: all three workflows pass on `main` at `374e167`,
with the container release target scoped to `linux/amd64`.

**Still not claimable:** arm64 container support or a multi-architecture image
(row 7.9 and its scope note), a public deployment or live URL (8.1), any link
between the served bundle and the locked metrics (3.3), and any capacity, SLO,
or savings figure beyond the measured loopback numbers (5.1, 6.2).
