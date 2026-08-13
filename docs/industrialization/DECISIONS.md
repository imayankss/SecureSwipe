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
