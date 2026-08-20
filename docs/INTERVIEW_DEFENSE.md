# Interview defense: design choices and trade-offs

## Five-minute explanation

SecureSwipe starts from an unusually imbalanced public credit-card dataset: 492
fraud rows among 284,807 transactions. The first engineering priority is not a
more fashionable model—it is controlling data and evidence. A strict contract
requires `Time`, `V1`–`V28`, `Amount`, and `Class` in canonical order, rejects
missing/non-finite/malformed/duplicate rows, fingerprints the dataset, and proves
row hashes are disjoint across new splits.

The repository separates four evidence types. The old random held-out result is
an immutable historical observation because it has already been seen. It is not
used again. New decisions belong to forward/blocked development folds that refit
preprocessing inside each fold. Calibration, confidence intervals, constrained
metrics, and cost sensitivity are implemented there. The original data/model is
absent, so the repository does not pretend those analyses have been executed on
the historical candidate.

The model boundary is one versioned ModelBundle: fitted preprocessor, estimator,
optional calibrator, operating point, ordered schema, model/data versions,
dependency/runtime metadata, sizes, and hashes. The service loads only an
operator-configured local bundle under a trusted root and validates it before
joblib deserialization. Evaluation and service paths share canonical batch
scoring, with golden tests proving identical outputs.

FastAPI exposes liveness, readiness, model-info, single/batch prediction, and
bounded Prometheus text. Schemas reject unknown/non-finite inputs and enforce
body/batch limits. Outputs distinguish raw score from calibrated probability.
Logs are JSON with request IDs but no transaction vectors or downstream
exception messages. Synchronous estimator work is threadpool-offloaded while
model access is serialized for estimator safety.

The public Next.js dashboard is intentionally static. A strict exporter checks
aggregate evidence and the historical hash lock; browser tests prove it never
calls live prediction. The Docker image is non-root, minimal, data/model-free,
and expects a read-only mounted bundle. Local API/load evidence exists, but the
stopped Docker daemon, absent original artifact/data, and unexecuted remote CI
remain explicit blockers. That is the central design principle: evidence before
claims.

## Likely questions

### Why not optimize accuracy?

At 0.1727% prevalence, predicting every row legitimate exceeds 99% accuracy and
detects no fraud. Average precision, recall/precision, constrained operating
metrics, confusion counts, and workload/cost sensitivity are more informative.

### Why is 0.53 not “the fraud threshold”?

It is a historical development operating point that met an observed recall
constraint on one validation split. Its uncertainty is material and no domain
owner supplied reviewed false-negative, false-positive, review, or recovery
costs. The code supports sensitivity analysis but does not convert examples into
policy.

### Why not call the XGBoost score a probability?

Class weighting changes score semantics, and calibration has not been proven on
the historical model. The API calls it `raw_score`. A probability field remains
null unless a calibrator is fit without test leakage, compared on disjoint data,
and included in the verified bundle.

### Why might Random Forest be preferable?

The recorded XGBoost average-precision advantage is only about 0.0004 on one
validation split. The predeclared rule chooses the simpler candidate when paired
blocked uncertainty and constrained metrics are within tolerance. Complexity is
not justified by rounded leaderboard rank.

### How is leakage controlled?

Preprocessing fits on model-training rows only; duplicates undergo manifested
curation; content hashes must be disjoint across chronological roles; calibration
fit, operating-point selection, and reusable forward backtest are separate; and the
already-observed Kaggle corpus is reference-only.

### Why use joblib at all if pickle is unsafe?

It matches the existing scikit-learn stack, but the API never loads user-supplied
bytes or paths. Operators select locally produced reviewed artifacts, and the
loader validates trusted location, manifest completeness, sizes, hashes, schema,
versions, and payload types before deserialization. This reduces risk; it does
not claim arbitrary pickle is safe.

### Why not Kubernetes, Kafka, or online retraining?

There is no measured traffic, latency, data-volume, or organizational requirement
that justifies them. A single verified bundle, one service, offline monitoring,
and a static dashboard make the important failure modes inspectable. Additional
infrastructure would add operational claims without evidence.

### What would you do next with the missing inputs?

Restore the Kaggle CSV only for reference curation; its historical overlap cannot
be reconstructed. Obtain a genuinely new authorized corpus, run manifested
curation and four-role training/bundle evaluation, then start Docker and pass
image smoke, scan, SBOM, parity, and repeated quality gates. Public provider
evaluation comes only after those steps and owner approval.
