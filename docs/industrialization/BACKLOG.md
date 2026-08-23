# Industrialization backlog

Status legend: `[ ]` open, `[~]` in progress, `[x]` verified complete,
`[B]` externally blocked.

## P0

- [x] Reject duplicate, missing, infinite, malformed, and out-of-contract dataset inputs.
- [x] Fingerprint datasets/rows and prove split row hashes do not overlap.
- [x] Preserve the historical result while removing unsupported unbiased/real-world/authorization claims.
- [x] Replace unchecked deserialization with trusted-root, checksum, manifest, type, schema, and runtime verification.
- [x] Add corrupt/mismatch/untrusted-path tests proving failure occurs before deserialization.
- [x] Prevent historical-derivative promotion with operator-attested exact-file
  approval, project-lineage taint, and verified curation-manifest provenance.
- [x] Reject invented score evidence by reloading the originating bundle and
  recomputing all scores, including a forged-score-plus-forged-hash test.

## P1 — scientific validity

- [x] Record that historical duplicate overlap is irrecoverable without retained
  row identities and make the entire observed corpus reference-only.
- [x] Implement and synthetic-test chronological versus random diagnostic evidence.
- [x] Execute synthetic paired uncertainty/simplicity selection through the
  development-to-bundle command.
- [B] Execute the same protocol on a genuinely new authorized real dataset;
  none is available in this workspace.
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
- [x] Record/verify positive-class semantics, SciPy/XGBoost runtime, and a
  checksummed full-path startup probe; Bundle Format v3 additionally binds strict
  producer policy, immutable provenance, and descriptor-safe artifact loading.
- [x] Add deterministic manifested duplicate curation with conflicting-label failure.
- [x] Enforce source-row fingerprint isolation across calibration, selection,
  reusable forward backtest, and the already-observed historical namespace.
- [x] Add a real development training-to-bundle command that persists the selected
  calibrator/threshold and evaluation/service golden parity evidence.
- [x] Make behavior-affecting code/seed/policy/calibration/threshold/role changes
  produce a distinct model version.
- [x] Resolve and audit separate deterministic Darwin and Linux CPU locks; Linux
  uses `xgboost-cpu` and contains no NVIDIA packages.
- [x] Retain the canonical new-source approval atomically; revalidate its exact
  schema, source checksum/reference, attestation, and reviewer during curated
  loading/training; bind it and the curation manifest into training evidence.

## P1 — API/container/operations

- [x] Implement live/readiness, model-info, single prediction, batch prediction, and bounded metrics endpoints.
- [x] Strict Pydantic request/response/error contracts and OpenAPI validation.
- [x] Unknown/non-finite/malformed/oversized/batch-limit/unavailable-model/concurrency tests.
- [x] Structured redacted JSON logs with request IDs and no transaction vectors.
- [x] Configurable explicit CORS allowlist and request-body cap.
- [x] Normalize framework-generated 404/405 errors into `ErrorResponse` and
  document runtime-parity 413/422/500/503 OpenAPI schemas.
- [x] Replace Dockerfile, add `.dockerignore`, non-root user, pinned runtime, and health check.
- [x] Remove the unnecessary package installer from the final runtime image.
- [x] Rebuild and test linux/arm64 image startup/readiness/inference from the final lock.
- [x] Scan the rebuilt image and produce an SPDX SBOM; individually reviewed
  no-fix Debian exceptions expire 2026-09-20.
- [x] Bind the final ARM64 image to its Git revision and retain checksummed raw
  Trivy JSON, SPDX 2.2 JSON, scanner/database metadata, full findings, and every
  exception disposition in durable repository evidence.
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
- [x] Add synthetic-only optional live API demo with static fallback,
  timeout/loading/error/empty/unavailable states and focused component/browser
  coverage; the Docker prerequisite and local API gates pass.
- [x] Derive production `connect-src` from a validated API origin and prove one
  complete-contract synthetic request in the production Chromium gate.
- [x] Add component, keyboard, accessibility, responsive, and browser-smoke tests.
- [x] Add Python lint/type/unit/integration/export-determinism gates.
- [x] Add frontend lint/type/test/build/data gates.
- [B] Execute dependency, secret/code, bundle, container-build, and scan
  workflows remotely; least-privilege definitions and local policy/dependency
  audits pass, while first GitHub/Docker-backed execution is externally blocked.
- [x] Scan full history without suppressing unverified/revoked-looking secret candidates.
- [x] Make frontend export verification dependency-free under `python3 -S` and
  qualify public historical/deployment claims in tested visible copy.
- [x] Add Dependabot for Python, npm, and Actions.
- [x] Add root LICENSE, CONTRIBUTING, SECURITY, and PR template.

## P2/P3

- [ ] Treat calibration/candidate/threshold reuse of
  `operating_point_selection` explicitly as joint tuning or add an independent role.
- [ ] Validate bundle score/calibrator semantics before deserialization.
- [ ] Separate project-audit output verification from mutating quality execution
  or document the `--check` side effects.
- [x] Reconcile the exit-control scorecard with the two completed unchanged cycles.
- [ ] Check original paths for symlinks before `resolve()` dereferences them.
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

- [~] No open P0 and all four confirmed P1 findings from the independent audit
  at `c942c05` are corrected; follow-up independent re-audit remains outstanding.
- [x] Evidence score >= 92/100 and every category >= 80%.
- [x] Two consecutive full quality-gate runs pass with no code changes between them.
- [x] Golden predictions identical in evaluation and API service paths on the
  deterministic new-development fixture; real-data execution is externally blocked.
- [x] Container startup/readiness/inference pass.
- [x] Security/dependency scans have no unresolved high/critical issue or justified exception.
- [ ] Independent adversarial re-audit finds no new P0/P1.
