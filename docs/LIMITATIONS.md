# Limitations and non-goals

This is the canonical statement of what SecureSwipe's current evidence and
implementation do not support. Architecture is described in
[ARCHITECTURE.md](ARCHITECTURE.md); release procedure and source-integrity checks
are described in [DEPLOYMENT.md](DEPLOYMENT.md).

These limits are claim controls. Changing wording does not remove them; changing
a limit requires new, reviewed evidence.

## Headline scientific evidence

- Lane A is one offline evaluation on the public IEEE-CIS research dataset. It
  does not establish performance for a merchant, geography, issuer, season,
  attack pattern, or future fraud distribution.
- The final role was programmatically held out by a frozen partition, not
  withheld by an independent party. The evaluation is not human-blind or
  externally blind.
- The final result was observed exactly once and is closed. It cannot be used to
  tune, refit, recalibrate, reselect features, choose a capacity, or rerun the
  evaluation.
- `TransactionDT` is a relative time offset. It does not support calendar,
  seasonal, holiday, or deployment-time claims.
- Confidence intervals quantify sampling variation under the recorded bootstrap
  procedure. They do not cover dataset shift, label error, adversarial response,
  or operating-process uncertainty.
- The upper calibration bins are empty on the observed Lane A population. That
  is reported as found and is not evidence that high-risk cases cannot exist
  elsewhere.

The complete result and its prohibited claims are in
[LANE_A_FINAL_EVALUATION.md](evidence/LANE_A_FINAL_EVALUATION.md).

## Lane A, Lane B, and the local demo

- Lane A and Lane B use different corpora, features, base rates, label
  definitions, partitions, and evidence lifecycles. Their metrics are not
  directly comparable.
- Lane A is the sole headline evaluation. Lane B remains an already-observed
  historical record and cannot drive new model or threshold choices.
- The original Lane B data/model/score artifacts and retained holdout identities
  are absent, so its ranking metrics cannot be independently reconstructed from
  a clean checkout.
- Historical duplicate contamination cannot be measured retrospectively because
  the original split identities were not retained.
- The exact sealed Lane A serving chain is unavailable or cryptographically
  unproven. P0.4 therefore prohibited reconstruction, approximation, or
  substitution.
- The `/demo` route is a local reference-model demonstration. It does not serve
  or claim to serve the Lane A headline model.
- A verified local reference bundle proves only its own bytes, schema,
  provenance metadata, and runtime behavior. It does not inherit Lane A or Lane
  B evaluation metrics.

See [EVIDENCE_GUIDE.md](EVIDENCE_GUIDE.md) for category ownership.

## Inputs, output, and model interpretation

- Anonymized PCA components do not support narratives about merchant, customer,
  device, geography, identity, or causality.
- The local historical/reference bundle emits `raw_score`. It is not established
  as a real-world fraud probability.
- A calibrated probability label is permitted only when a disjointly fitted and
  evaluated calibrator is packaged and identified for that exact bundle.
- An operating threshold or capacity frontier is a recorded review policy for a
  named evidence context. It is not a universal business rule.
- `human_review` and `below_review_threshold` are queueing signals. Neither is an
  approval, decline, block, capture, refund, investigation, or report to an
  external party.
- No real merchant feedback loop, appeal process, reviewer outcome store, label
  maturation workflow, or automatic retraining path is implemented.

## Review capacity

- Capacity tiers are illustrative workload analyses, not staffing
  recommendations, service commitments, or merchant defaults.
- Increasing capacity raises recall and also raises the number of legitimate
  transactions sent to human review.
- A false positive means a legitimate transaction selected for review. It does
  not mean an automatically rejected payment.
- The retrospective workload required to cross a recall target is a diagnostic
  on the evaluated population, not a forward guarantee.
- Queue arrival patterns, reviewer skill, prioritization changes, duplicate case
  handling, service hours, escalations, and delayed outcomes are outside the
  capacity calculation.

## Illustrative cost analysis

- Cost outputs are deterministic arithmetic over published aggregate counts and
  editable assumptions. They are not observed merchant economics.
- The model omits fixed staffing steps, queueing, time-varying volume, delayed
  labels, appeals, customer remediation, and uncertainty in recovery value.
- No tier is identified as optimal, recommended, cheaper in reality, or a
  production threshold.
- No output is a saving, ROI, avoided loss, payback, net benefit, or forecast.
- Currency-labelled inputs are illustrative starting assumptions, not prices or
  defaults supplied by Razorpay or a merchant.

The formula and sensitivity boundary are canonical in
[MT5_COST_EXPLORER_EVIDENCE.md](evidence/MT5_COST_EXPLORER_EVIDENCE.md).

## Explainability and fairness

- SHAP describes model attribution under a declared output unit; it is not a
  causal explanation.
- PCA features reduce semantic interpretability, and historical attribution
  artifacts lack the complete row/output-unit evidence required for a stronger
  claim.
- Protected attributes are absent. Demographic parity, equalized odds, subgroup
  recall, and related protected-group analyses cannot be computed from this
  dataset.
- PCA axes must not be treated as proxies for protected characteristics.
- Not observing a disparity is not evidence of fairness.

## Serving and state

- The FastAPI service is a local/container reference, not a public transaction
  service.
- Estimator access is serialized. Threadpool offload prevents event-loop
  blocking but does not make arbitrary estimators concurrently safe.
- Timeouts bound the client wait, not the underlying Python thread. A timed-out
  worker retains its admission slot until it actually finishes.
- Admission control fails closed at the configured in-flight limit. It does not
  provide a durable queue or backpressure across processes.
- Default idempotency is in-process only. It is lost on restart and is not shared
  across workers or replicas.
- Same-process replays can return the original response and committed audit
  receipt without a duplicate append. That does not establish cross-restart
  exactly-once behavior.
- The optional SQLite durability implementation is a local, non-default
  prototype outside the API request path. It is not multi-writer, distributed,
  highly available, or cross-host state.
- Audit NDJSON and its local head anchor are tamper-evident, not immutable,
  remotely anchored, replicated, or WORM storage.
- An actor able to rewrite both the log and its anchor can manufacture a new
  internally valid history.
- Partial audit writes and anchor mismatches require operator preservation and
  recovery; the service does not silently bypass them.

Detailed fault evidence is in
[MT6_STATE_AND_CRASH_DECISION.md](evidence/MT6_STATE_AND_CRASH_DECISION.md).

## Performance and capacity evidence

- All recorded serving measurements are local loopback tests. They exclude an
  external network, TLS, proxy, browser distance, cloud cold start, and competing
  tenants.
- The measured service used one machine, one process, and one worker. It does
  not establish multi-replica scaling.
- The benchmark serves a historical/reference bundle, not the Lane A model, and
  says nothing about fraud-detection quality.
- Throughput, latency percentiles, and audit-growth measurements are descriptive
  for their recorded environment. They are not a production SLO or capacity
  commitment.
- Audit append verifies the prior chain and therefore grows with history. That
  bounded-growth evidence must remain attached to any throughput discussion.
- The earlier logistic-regression benchmark is synthetic plumbing evidence, not
  genuine fraud-model performance.

Use [MT4_CONCURRENCY_EVIDENCE.md](evidence/MT4_CONCURRENCY_EVIDENCE.md) for the
measured values and environment.

## Security and privacy

- The service has no implemented customer authentication, authorization,
  enterprise identity, tenant isolation, public rate limiter, WAF, DDoS layer,
  TLS termination, production key management, or transaction store.
- Checksum and trusted-root verification reduce artifact substitution risk but
  do not make arbitrary pickle/joblib safe. Only locally produced, reviewed
  bundles are eligible.
- Raw data, model files, environment files, and local artifacts are ignored, but
  ignore rules are not a data-governance or exfiltration control.
- The audit allowlist and request logging avoid raw features and common sensitive
  fields; they do not establish a real-data privacy program.
- No PCI DSS, SOC 2, ISO 27001, GDPR, RBI, penetration-test, bank-grade, or other
  compliance/certification claim is made.
- The repository must not receive real PAN, CVV, customer identity, credentials,
  or transaction data.

See [THREAT_MODEL.md](THREAT_MODEL.md) for threats and residual risks.

## Operations and deployment

- No public backend is verified by the repository.
- A reachable static URL does not prove which source revision produced it.
- No public dashboard may be called the current candidate until the source SHA,
  build inputs, immutable output identity, and served content are linked by the
  [P0.5 procedure](DEPLOYMENT.md#p05-deployment-to-source-sha-integrity).
- Provider authentication, routing, DNS, retention, monitoring ownership,
  rollback, and cost controls remain external operational decisions.
- The container release target and architecture-specific evidence must remain
  attached to the exact CI/container record; local success is not a release.
- Drift diagnostics open an investigation. They do not automatically retrain,
  change thresholds, roll back, or deploy.

Current and historical deployment evidence is owned by
[DEPLOYMENT.md](DEPLOYMENT.md) and the
[claim-to-evidence matrix](evidence/CLAIM_TO_EVIDENCE_MATRIX.md#8--deployment-status),
not by this limitations page.

## Separate prototypes and deferred work

- Synthetic order integrity is a pre-model reference using fabricated catalog
  data. It is not a payment gateway integration, real incident control, fraud
  metric, or production workflow.
- The Razorpay context adapter is deferred and not implemented. No Razorpay API,
  SDK, MCP, webhook, key, secret, credential, or field mapping is used.
- Reference descriptions of queues, shared state, replicas, or hosted monitoring
  are not implemented architecture.

## Explicit non-goals

- Real payment authorization or automated adverse action.
- Raw transaction ingestion, customer identity processing, or card-data storage.
- A public fraud-scoring API or live merchant integration.
- Fabricated costs, SLOs, savings, capacity, security certification, or evidence.
- Reusing a historical or sealed final result for model selection.
- Presenting a reference/demo bundle as the Lane A headline model.

## Evidence required to change a limitation

A limitation changes only when the relevant canonical record receives new,
reviewed evidence. Depending on the claim, that can require an authorized new
source; frozen development and final protocols; an exact verified bundle chain;
direct/single/batch parity; public-network and provider measurement;
authentication and privacy review; durable shared state; rollback rehearsal; or
deployment-to-source-SHA proof.

Until that evidence exists, the limitation remains in force.
