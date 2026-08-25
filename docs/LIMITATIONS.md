# Limitations and non-goals

This document states what the current evidence does not support. These limits
are release controls, not a roadmap that can be waived by changing wording.

## Scientific limitations

- The tracked test result is a single already-observed random holdout, not an
  out-of-time or real-world performance estimate. The raw CSV, fitted artifact,
  score vector, and original runtime manifest are absent.
- Historical EDA recorded 1,081 exact duplicate rows. The original split did not
  group or reject them, and holdout row identities were not retained, so its
  cross-split overlap cannot be reconstructed even after restoring the CSV. The
  exact corpus is reference-only; new data uses manifested curation.
- XGBoost's recorded validation average-precision advantage over Random Forest
  is about 0.0004 on one split. That does not establish material superiority;
  it remains historical only. The executable rule is proved with synthetic
  new-data fixtures but has not run on a real new authorized corpus.
- The historical `0.53` threshold met a point recall constraint on one validation
  sample. It is not a business policy, guarantee, or cost optimum. Cost examples
  in code use explicit synthetic unitless assumptions.
- The class-weighted XGBoost output is an uncalibrated raw score. A calibrated
  probability may only be exposed when a disjointly fit/evaluated calibrator is
  packaged and identified in the bundle.

## Data, fairness, and explainability limitations

- `V1`–`V28` are anonymized PCA components. They do not support merchant,
  customer, location, device, or causal narratives.
- No protected-group attributes are present. Demographic parity, equalized odds,
  subgroup recall, and other protected-group fairness evaluations cannot be
  performed from these fields. Absence of an observed disparity is not claimed.
- SHAP is a model-attribution method, not a causal explanation. The tracked
  historical ranking lacks retained row identities, score/label composition,
  declared output unit, and additivity residual, so it remains explicitly
  unverified. New XGBoost runs verify raw-margin additivity and disclose cohorts.
- The dataset is old, anonymized, and not a representative sample of every
  geography, issuer, merchant, attack pattern, or operational review process.

## Service and security limitations

- The API is a local/container reference. It has no implemented customer
  authentication, public rate limiter, TLS termination, enterprise identity,
  multi-tenancy, transaction store, or real-data privacy program.
- API idempotency is in-process only and is lost on restart; it is not shared
  across workers or replicas. The optional hash-chained audit log and local head
  anchor are tamper-evident, not immutable, remotely anchored, or WORM storage.
- A transient audit-sink failure before append can be retried after recovery.
  Partial writes or log/anchor integrity failures remain unavailable until an
  operator preserves and repairs or rotates the sink; there is no automatic
  bypass, distributed failover, or circuit breaker.
- Checksum and trusted-root verification reduce artifact substitution risk but
  do not make untrusted pickle/joblib safe. Only locally produced, reviewed
  bundles are eligible.
- The service returns bounded `human_review` or `below_review_threshold`
  signals; it does not approve, decline, block, investigate, or report a
  financial transaction.
- No PCI DSS, regulatory, bank-grade, penetration-test, availability, or
  production-customer claim is made.

## Operational and deployment limitations

- The current genuine-model load numbers use the selected historical-reference
  XGBoost bundle on one loopback Apple M2 process with one fixed input. They do
  not measure Docker, cloud/server-internal cold start, external network paths,
  audit persistence overhead, autoscaling, competing traffic, or customers. The
  prior logistic-regression numbers remain synthetic plumbing evidence only.
- The container release target is `linux/amd64` only. That architecture is
  built, smoke-tested, vulnerability-scanned, and SBOM-generated in CI. A native
  arm64 image has passed the same restricted startup, liveness, readiness, and
  synthetic inference smoke locally, but that is a local development
  convenience, not a released or CI-gated artifact.
- **No arm64 container support is claimed.** The emulated `linux/arm64` CI leg
  is deferred: under QEMU on GitHub-hosted runners the container never completes
  application startup, so the readiness loop exhausts and the job fails. This
  reproduced deterministically three times, did not reproduce on native arm64 or
  Rosetta-emulated amd64, and was not root caused. See `docs/CONTAINER.md`.
- Drift metrics are diagnostic signals. They do not prove model failure and do
  not trigger automatic retraining, threshold changes, rollback, or deployment.
- SecureSwipe has no independently verified current release-candidate public
  deployment. Any prior static URL is not evidence for this candidate. The
  static dashboard will be deployed and verified only after final CI passes.

## Explicit non-goals

- Real payment authorization or automated adverse action.
- Raw transaction ingestion, storage, or customer identity processing.
- Kubernetes, Kafka, Spark, a microservice fleet, online feature stores, or
  automatic retraining without a demonstrated requirement.
- Fabricated costs, SLOs, capacity, security certification, or screenshots.
- Reusing the historical test to select a model, calibrator, threshold, or
  monitoring policy.

## Evidence required to change these limits

Changing a limitation requires generated evidence: the authorized original data
for forward/paired/calibration analysis; a complete reviewed ModelBundle; Docker
startup/readiness/inference plus image scan/SBOM; remote CI execution; and, for a
public service, an owner-approved threat/risk review with authentication, TLS,
rate limits, retention, provider measurement, rollback rehearsal, and cost.
