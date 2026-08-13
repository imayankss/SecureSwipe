# Industrialization decision log

## D-001 — Preserve the historical test result as an observation

Status: accepted

The tracked random held-out result remains a historical artifact because Git
history supports model/threshold selection preceding the recorded evaluation.
It is now observed and is excluded from every new decision. It will not be
silently regenerated, retuned, or relabeled as out-of-time evidence. Public
language will identify the possible duplicate contamination and absent runtime
provenance.

## D-002 — Development decisions use blocked time protocols

Status: accepted, original-data execution blocked

New model, calibration, and threshold decisions will use training/development
data with forward/blocked evaluation. A comparison with the old random
development protocol will quantify optimism. The historical test is not used.

## D-003 — Duplicate rows fail the canonical dataset contract

Status: accepted

Exact duplicates are rejected before splitting. This is easier to audit than
allowing row-level duplicates and prevents identical rows crossing boundaries.
The manifest records duplicate count/policy and deterministic fingerprints.
If a future domain owner needs repeated legitimate events, that requires an
explicit entity/event identifier and grouped policy rather than indistinguishable
row duplication.

## D-004 — Keep the existing stack; do not add distributed infrastructure

Status: accepted

FastAPI, the current Python ML stack, a single versioned bundle, Next.js, and
local/container tooling are sufficient for a portfolio reference. Kubernetes,
Kafka, Spark, and a service fleet have no demonstrated requirement.

## D-005 — Model artifacts are server-configured, local, and verified

Status: accepted

The API never accepts model bytes or paths from requests. A bundle must resolve
inside a configured trusted root and pass manifest, size, checksum, schema,
runtime, dependency, and payload-type checks before use. Checksums establish
integrity, not the safety of arbitrary pickle content; only locally produced,
reviewed artifacts are trusted. Missing bundles make readiness/inference fail
closed while liveness remains available.

## D-006 — Uncalibrated output is a raw score

Status: accepted

The class-weighted XGBoost output is named `raw_score`. `calibrated_probability`
is nullable and only populated when a calibrator has been fit on development
data, evaluated, and packaged. The response states the decision basis and
threshold explicitly.

## D-007 — Prefer simpler models within an uncertainty/tolerance margin

Status: accepted, protocol implementation pending

A complex model is not selected for a rounded 0.0004 AP advantage. Paired
blocked evaluation and uncertainty intervals will be used. When operationally
relevant constrained metrics are comparable within a predeclared margin, the
simpler model wins.

## D-008 — Static dashboard remains the safe default

Status: accepted

The existing static evaluation dashboard is preserved. Optional live demo mode
will be enabled only after local/container API gates pass, will use synthetic
examples, and will retain timeout/error/static fallbacks. No frontend secret uses
`NEXT_PUBLIC_*`.

## D-009 — Deployment and publication remain explicit external actions

Status: accepted

Local installs, tests, edits, and commits are authorized. Pushes, pull requests,
releases, public deployments, DNS, and paid infrastructure require explicit
confirmation immediately before the action.

## D-010 — Separate hash-locked service and quality environments

Status: accepted

`requirements/api.lock` contains only the production API closure and hashes;
`requirements/quality.lock` adds training and verification tools. Human-reviewed
top-level `.in` files are the source of each lock. Notebook tooling remains an
explicit optional input rather than inflating the service or ordinary test
environment. Locks target Python 3.12 and CPU execution on Apple Silicon/Linux;
CUDA is neither required nor selected.

## D-011 — Missing artifacts mean not-ready, invalid artifacts abort startup

Status: accepted

An image or developer process may start without a model so liveness and
diagnostics remain available, but readiness and inference return 503. Once a
bundle path is explicitly configured, any trust, provenance, checksum, schema,
or runtime failure aborts startup. This avoids silently serving a fallback model.

## D-012 — Model bundles are mounted, not baked into the service image

Status: accepted

The image and model have independent immutable identities. Production source,
dependencies, and user privileges are testable without distributing a private
dataset or artifact in the build context. A reviewed bundle is mounted read-only
and selected by a server-side manifest path. Replacement or rollback starts a
new container with another versioned bundle; bundles are never edited in place.

## D-013 — Calibration comparison requires disjoint row identity

Status: accepted

The calibrator-training and calibration-evaluation partitions supply globally
meaningful row IDs. The comparison rejects duplicates within either side and
any cross-partition intersection before fitting. Platt/isotonic are compared
against identity using Brier score and calibration error; identity wins ties and
an explicitly recorded improvement margin controls whether calibration is used.

## D-014 — Cost outputs are sensitivity evidence, not business policy

Status: accepted

Every scenario supplies non-negative false-positive, false-negative, and review
cost plus a recovery rate. The report exposes component totals and review volume.
Example scenarios are synthetic unitless ratios and cannot justify a threshold.
A domain owner must provide reviewed assumptions before cost-based selection.

## D-015 — Run manifests omit wall-clock timestamps

Status: accepted

Evidence manifests record code commit/dirty-diff digest, input/output hashes,
parameters, seeds, runtime versions, and evaluation namespace. Excluding the wall
clock makes identical inputs/code produce identical manifests; external job or
artifact systems may record creation time separately without changing evidence.

## D-016 — File presence is never a passing audit gate

Status: accepted

The current project audit uses `PRESENT` for non-empty inventory entries and
reserves `PASS` for commands or verified bundles that actually execute. Missing
model configuration is `UNAVAILABLE`, not a stale historical PASS. The report
remains `INCOMPLETE` even when static-checkout gates succeed without a model.

## D-017 — Historical `pr_auc` keys mean average precision

Status: accepted

Existing JSON keys remain for compatibility, but UI/report labels now state
average precision because the implementation used `average_precision_score`.
The exporter does not relabel it as trapezoidal area under the PR curve.

## D-018 — CI verifies but never publishes

Status: accepted

Pull requests and main-branch updates run separate quality, security, and
container evidence workflows. Their default token permission is read-only and
all external actions use immutable revisions. The workflows do not deploy,
publish packages/images, create releases, or auto-merge. Publication remains a
separate owner-authorized action, and workflow definitions are not called
passing evidence until GitHub actually executes them.

## D-019 — Pin the lock generator, including pip

Status: accepted

The quality input includes pip 25.3 and pip-tools 7.5.2 because the latter uses
an internal API removed by pip 26. Lock generation always runs from the
`requirements/` directory with the command recorded in the lock header. Two
consecutive generations must have the same digest; dependency update PRs must
review both top-level intent and the resolved hash diff.

## D-020 — Drift opens an investigation; it does not declare failure

Status: accepted

Offline monitoring validates schema before scoring and emits aggregate feature,
decision-score, and optional delayed-label diagnostics. PSI/KS thresholds are
operational signals rather than causal/statistical proof. No signal changes a
threshold, retrains, deploys, or rolls back automatically. Raw-score calibration
diagnostics are never described as evidence of real probability calibration.

## D-021 — Preserve event-loop health while serializing estimator access

Status: accepted

FastAPI endpoints offload synchronous pandas/preprocessor/model work to the
framework threadpool, so liveness and metrics are not held behind CPU-bound
request execution. The model service lock remains the single estimator-access
boundary because concurrent safety is not assumed for arbitrary fitted objects.
Measured scaling claims require the actual candidate model and container.

## D-022 — Local measurements are regression evidence, not deployment SLOs

Status: accepted

The bounded harness accepts loopback targets only, warms up once, validates the
response contract, probes liveness during load, and records runtime and latency
percentiles. Local regression objectives use twice the worst observed values
from repeated M2 synthetic runs. No container/provider/customer SLO exists until
those environments and failure modes are measured.

## D-023 — The historical test namespace is verify-only

Status: accepted

The tracked final JSON, generated report, and selected validation threshold are
coupled by a reviewed SHA-256 lock. The legacy final runner has no data/model
execution path and refuses ordinary invocation. A guarded one-time metadata
migration changed only terminology/provenance fields, verified the exact source
hashes, and left recorded metrics unchanged. New work must use an explicit
development/forward namespace; changing the lock and evidence together requires
normal code review and is never presented as new test evidence.

## D-024 — One strict configuration owns offline defaults

Status: accepted

`configs/config.yaml` is validated with frozen Pydantic models and rejects
unknown fields, invalid split/policy values, and artifact directories outside
the trusted root. Active day runners derive their paths and operating-point
defaults from it. Randomized modules import the canonical seed from one feature
configuration module, and a contract test proves that value matches the typed
configuration. API runtime settings remain environment-owned because container
mounts, body limits, and CORS are deployment inputs rather than training facts.
