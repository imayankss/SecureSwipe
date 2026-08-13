# Industrialization backlog

Status legend: `[ ]` open, `[~]` in progress, `[x]` verified complete,
`[B]` externally blocked.

## P0

- [x] Reject duplicate, missing, infinite, malformed, and out-of-contract dataset inputs.
- [x] Fingerprint datasets/rows and prove split row hashes do not overlap.
- [x] Preserve the historical result while removing unsupported unbiased/real-world/authorization claims.
- [x] Replace unchecked deserialization with trusted-root, checksum, manifest, type, schema, and runtime verification.
- [x] Add corrupt/mismatch/untrusted-path tests proving failure occurs before deserialization.

## P1 — scientific validity

- [B] Measure duplicate overlap in the original historical split; requires the local Kaggle CSV.
- [B] Execute deterministic blocked/out-of-time development evaluation and compare it with random development splits; synthetic-tested forward protocol is implemented, original CSV is absent.
- [B] Execute paired uncertainty analysis for Random Forest versus XGBoost; bootstrap and simplicity/tie policy are implemented, paired original scores are absent.
- [x] Add bootstrap/Wilson confidence intervals for core classification metrics.
- [x] Implement Brier score, reliability data, ECE, and leakage-safe Platt/isotonic comparison.
- [x] Implement configurable FP/FN/review/recovery cost scenarios and threshold sensitivity.
- [x] Add recall at precision/FPR constraints and name average precision accurately.
- [x] Add fail-closed XGBoost raw-margin SHAP additivity and cohort-evidence protocol.
- [B] Apply the verified SHAP protocol to the historical model; the artifact and
  aligned sample row identities are absent, so the tracked ranking is explicitly unverified.
- [x] Write data card, model card, and protected-group fairness limitation.

## P1 — artifacts and reproducibility

- [x] Consolidate typed configuration and deterministic seeds.
- [x] Add versioned `ModelBundle` with preprocessor, model, optional calibrator,
  threshold, ordered schema, runtime versions, data fingerprint, version, and checksums.
- [x] Add deterministic run manifests including code SHA and input/artifact hashes;
  legacy direct CLIs now refuse execution and the atomic reference wrapper covers Day 2–7.
- [x] Add golden evaluation/service prediction parity tests.
- [x] Make service startup fail closed on incomplete/corrupt/mismatched bundles.
- [x] Separate and hash-lock API runtime and quality dependency sets; keep notebook tooling optional.
- [x] Build/install a wheel in a clean environment.
- [x] Build the wheel through a fresh sdist boundary and reject missing/stale modules.
- [x] Protect historical test outputs from accidental overwrite and separate result namespaces.

## P1 — API/container/operations

- [x] Implement live/readiness, model-info, single prediction, batch prediction, and bounded metrics endpoints.
- [x] Strict Pydantic request/response/error contracts and OpenAPI validation.
- [x] Unknown/non-finite/malformed/oversized/batch-limit/unavailable-model/concurrency tests.
- [x] Structured redacted JSON logs with request IDs and no transaction vectors.
- [x] Configurable explicit CORS allowlist and request-body cap.
- [x] Replace Dockerfile, add `.dockerignore`, non-root user, pinned runtime, and health check.
- [B] Test linux/arm64 image startup/readiness/inference; Docker Desktop must be started.
- [B] Scan image and produce SBOM; Docker Desktop must be started.
- [x] Add bounded latency/request/error/score-distribution metrics.
- [x] Implement deterministic offline drift monitor with synthetic shifted demonstration.
- [x] Run local load test and record p50/p95/p99/error rate.
- [B] Create measured provider/container SLOs; host measurement and local
  alert/incident/rollback/model-replacement guidance are complete, while Docker
  and a selected provider remain external prerequisites.

## P1 — frontend/QA/supply chain

- [x] Make export check side-effect-free and checksum every public artifact.
- [x] Fully validate metric/confusion/threshold invariants and tamper cases.
- [x] Gate frontend build on export verification.
- [B] Add synthetic-only optional live API demo with static fallback,
  timeout/loading/error/empty states; deliberately gated on Docker image startup,
  readiness, inference, and scan evidence.
- [x] Add component, keyboard, accessibility, responsive, and browser-smoke tests.
- [x] Add Python lint/type/unit/integration/export-determinism gates.
- [x] Add frontend lint/type/test/build/data gates.
- [B] Execute dependency, secret/code, bundle, container-build, and scan
  workflows remotely; least-privilege definitions and local policy/dependency
  audits pass, while first GitHub/Docker-backed execution is externally blocked.
- [x] Add Dependabot for Python, npm, and Actions.
- [x] Add root LICENSE, CONTRIBUTING, SECURITY, and PR template.

## P2/P3

- [x] Remove or explicitly deprecate dead placeholder modules and stale reports after call-graph verification.
- [x] Add skip link/mobile navigation/progress/table/chart accessibility semantics.
- [x] Record a frontend performance budget from a clean measured build.
- [x] Correct project author metadata.
- [x] Write architecture, ADRs, deployment/reproducibility guides,
  limitations/non-goals,
  interview defense, and three-minute demo script.
- [x] Write and locally verify an explicit threat model.
- [x] Write monitoring interpretation and local incident/rollback guidance.
- [B] Evaluate deployment providers only after the Docker/local gates pass;
  current prices/limits require research at selection time and external action
  requires explicit approval.

## Exit audit

- [B] No open locally actionable P0/P1; original data/model, Docker, remote CI,
  and public integration prerequisites are documented external blockers.
- [ ] Evidence score >= 92/100 and every category >= 80%.
- [ ] Two consecutive full quality-gate runs pass with no code changes between them.
- [ ] Golden predictions identical in evaluation and API service paths.
- [ ] Container startup/readiness/inference pass.
- [ ] Security/dependency scans have no unresolved high/critical issue or justified exception.
- [ ] Independent adversarial re-audit finds no new P0/P1.
