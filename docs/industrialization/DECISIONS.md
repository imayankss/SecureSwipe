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

Status: accepted, real new-data execution blocked

New model, calibration, and threshold decisions use genuinely new authorized
data with four chronological roles and a reusable forward backtest. A random-split
diagnostic is recorded but cannot choose a model. The historical Kaggle corpus
and its observed test are ineligible.

## D-003 — Duplicates require manifested deterministic curation

Status: accepted

Conflicting-label feature duplicates fail. Otherwise, curation keeps the first
exact feature vector in stable source order and records raw/curated hashes,
removed class counts, and decision eligibility; downstream contracts reject any
unresolved duplicate. This prevents identical rows crossing boundaries.
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

Status: accepted and implemented

A complex model is not selected for a rounded 0.0004 AP advantage. The new-data
workflow uses unrounded chronological-selection AP, paired stratified bootstrap,
and a recorded margin. Candidate order encodes simplicity; the first candidate
within the predeclared margin of the best AP wins and is freshly refit on the
model-training role only.

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

The `api` locks contain only the production API closure and hashes; the
`quality` locks add training and verification tools. Darwin and Linux variants
are resolved separately (D-034). Human-reviewed
top-level `.in` files are the source of each lock. Notebook tooling remains an
explicit optional input rather than inflating the service or ordinary test
environment. Locks target Python 3.12 and CPU execution; CUDA is neither
required nor selected.

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

The calibration-fit and operating-point-selection partitions supply
content-derived row fingerprints verified against the curated source. The
workflow rejects duplicates or any cross-role intersection. Platt/isotonic are compared
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

Status: superseded by D-028

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

## D-025 — SHAP explains verified raw margin on disclosed cohorts

Status: accepted

New XGBoost explanations use TreeExplainer raw output and must reconstruct the
model's native `output_margin=True` for every explained row. The resulting unit
is raw margin/log-odds, never calibrated probability. A disjoint purposeful
cohort includes labelled-fraud, highest remaining raw-score, and deterministic
random rows; its aggregate label/score composition and per-cohort rankings are
reported as non-prevalence-representative. Historical values are not upgraded by
the new protocol: their artifact, row identities, output unit, and residuals are
absent, so public material labels them unverified.

## D-026 — Multi-file evidence publishes atomically or not at all

Status: accepted

Development analysis and legacy reference stages write into a sibling temporary
directory and rename it only after every output and strict run manifest closes
successfully. Existing targets, including empty directories and symlinks, are
never overwritten; injected failure leaves no apparently complete target. Wall
timestamps were removed from generated reports, so equal inputs/code/runtime
produce byte-identical evidence in separate targets. Direct Day 2–7 CLIs refuse
execution; `run_reference_stage.py` is the manifested compatibility boundary and
its `legacy_random_*_reference` scopes are ineligible for new decisions.

## D-027 — Browser behavior is tested; live mode is synthetic and opt-in

Status: accepted

Vitest and Testing Library cover deterministic component interaction and
screen-reader semantics without expanding the runtime bundle. A single
Playwright Chromium gate exercises the production build, responsive/keyboard
navigation, a WCAG A/AA Axe scan, the static no-inference boundary, and the
unconfigured live-demo fallback. The optional demo is enabled only by the
build-time `NEXT_PUBLIC_SECURESWIPE_API_URL` setting, posts one fixed all-zero
synthetic feature vector to `/v1/predict`, aborts after three seconds, and
preserves the static example for loading, timeout, unavailable, empty, and
error outcomes. It must never accept transaction input or imply real-data
serving. Multiple browser engines have no demonstrated reference-project
benefit.

## D-028 — Isolate the current lock generator from the quality runtime

Status: accepted

Four 2026 advisories made pip 25.3 unsuitable even for the contributor
environment. The quality input now pins fixed pip 26.2.1 and no longer installs
pip-tools. Lock generation uses the separate hash-locked `lock-tools.lock` with
pip 26.2.1 and pip-tools 7.6.1 in a disposable virtual environment. This keeps
the resolver reproducible without making it part of ordinary test/training
execution. Both locks must compile byte-identically twice, and the quality lock
must pass `pip-audit` before review.

## D-029 — Build release wheels through a fresh sdist boundary

Status: accepted

Direct `python -m build --wheel` can reuse ignored `build/lib` contents and
silently package modules deleted from the worktree. Release gates therefore run
`python -m build --no-isolation`, which creates the sdist and builds the wheel
from its fresh temporary extraction using the already locked build backend. A
second executable gate compares every packaged `api/` and `src/` Python member
against the current source tree and rejects either missing or unexpected files.

## D-030 — The runtime image has no package installer

Status: accepted and container-verified

The final API image never installs packages after construction, so it removes
the Python base image's pip before switching to the non-root user. This avoids
shipping an unnecessary installer and its advisory surface. Dependencies remain
installed only in the build stage from the hash-locked API closure. A clean
pip-free virtual-environment proof imports the wheel successfully. The final
ARM64 image also passed non-root/read-only startup, readiness, exact golden
inference, bounded load, reviewed Trivy high/critical scanning, and SBOM gates.

## D-031 — Bundle readiness includes class semantics and a golden runtime probe

Status: accepted

Bundle Format v3 records the fraud label and its exact probability-column index,
rejects any model or probabilistic calibrator whose fitted classes are not
exactly `[0, 1]`, and records SciPy/XGBoost alongside the core Python runtime.
It also binds immutable intended-use, threshold, producer-policy, recipe, data-role,
and quarantine provenance. Every manifest field, payload hash, and runtime
dependency is verified before deserialization from the exact retained byte
snapshot. After deserialization, a checksummed fixed synthetic raw-feature probe
must traverse the fitted preprocessor, estimator, optional calibrator, and
score-integrity checks within a fixed numerical tolerance before the bundle can become ready.
The probe contains no source transaction. Container CI compares the complete
synthetic response and checks the final UID and absence of pip; this workflow is
still intent, not execution evidence, until Docker/GitHub run it.

## D-032 — Source eligibility is an explicit reviewed trust boundary

Status: accepted

The historical holdout row identities were not retained, so bytes alone cannot
prove that a new file is unrelated. The configured Kaggle path and known
284,807-row/492-fraud signature are ineligible. Project-created historical
derivatives propagate taint when their verified lineage accompanies the CSV.
Decision-eligible curation additionally requires an accountable reviewer to approve
the exact file checksum, source reference, and fixed non-derivation attestation.
This is deliberately documented as operator-attested provenance, not a technical
guarantee that a detached/copy-modified derivative can be detected.

Decision-eligible evidence requires a separately authorized source and four
chronological, content-hash-isolated roles: model training, calibration fit,
operating-point selection, and a reusable forward development backtest. The
random comparison uses matched row/class budgets and excludes calibration and
backtest rows. Candidate-versus-best paired intervals participate in the
predeclared simplicity decision. Calibration and threshold choices are fixed
before the backtest. Publication atomically couples metrics, lineage, scores,
the fitted bundle, and direct/reloaded/API parity.

## D-033 — Imported score files cannot create scientific evidence

Status: accepted

Post-training cost analysis accepts only a score file declared and hashed by a
verified development-training run manifest. It verifies the curated input and
lineage artifacts, loads that run's trusted ModelBundle, and recomputes every raw
score from source features before producing diagnostics. Calibration policy and
operating threshold remain frozen. A caller-supplied score CSV cannot generate a
new evaluation result, and the final chronological role is named a reusable
development backtest rather than an “untouched once” release test.

Model version is a behavioral identity: its digest covers model/preprocessor/
calibrator state, threshold, score semantics, role fingerprints, data lineage,
and decision-policy parameters. Any behavior-affecting change must yield a
different version exposed consistently by API, monitoring, and evidence.

## D-034 — Resolve Darwin and Linux dependency closures separately

Status: accepted

One marker-heavy lock did not reproduce correctly across Apple Silicon and
Linux: Darwin resolution omitted the Linux-only CPU distribution, while the
default Linux XGBoost distribution introduced CUDA/NCCL artifacts. The project
therefore compiles four hash-locked closures from shared pinned inputs. Darwin
uses `xgboost`; Linux uses `xgboost-cpu`. CI tests assert that Linux locks contain
the CPU distribution and no NVIDIA packages. Docker and Linux workflows never
install the Darwin lock.

## D-035 — Pin reviewed OS fixes and expire every scan exception

Status: accepted

The runtime starts from a reviewed multi-architecture Python 3.12.13 Trixie
digest and installs only explicit Debian security-update versions rather than a
floating full-system upgrade. The final image digest remains the deployable
identity. Trivy high/critical scanning has no blanket `ignore-unfixed` switch:
each residual no-fix Debian advisory is listed separately with a mitigation and
a 2026-09-20 expiry. Any new, fixed, or expired finding fails the gate and must
be reviewed against a rebuilt image.
