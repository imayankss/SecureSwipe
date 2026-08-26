# SecureSwipe pre-registered scientific protocol

**Status of this entire document: `PROPOSED` / `FUTURE/REFERENCE`.** Nothing here
has been executed. No model was trained, no calibrator was fitted, no threshold
was selected, no prediction was generated, and no held-out test outcome was
inspected while writing it. It is a pre-registration: the decisions below are
fixed *before* data access so that later results cannot be selected after the
fact.

- **Written at:** `501d8a6d7d2db48397b355aab592d6ea359ae277`, branch
  `codex/recovered-demo-bundle`. Branch-local; not on `main`.
- **Basis:** the accepted MT0 baseline and MT1 claim reconciliation, plus a
  read-only inspection of the curation, split, preprocessing, model, threshold,
  calibration, bundle, and evaluation source at this SHA.
- **Authority:** if executed results diverge from this document, **this document
  wins** and the divergence is reported as a protocol deviation, never silently
  absorbed.

---

## 1 — Evidence status and current blockers

Everything in this section is a statement about *what is missing now*. Each is a
precondition; §8 turns them into stop conditions.

| Item | Status | Detail |
|---|---|---|
| Raw `creditcard.csv` | `BLOCKED` | Absent. `data/raw/`, `data/interim/`, `data/processed/`, and `models/` contain only `.gitkeep`. |
| Dataset licence | `BLOCKED` | No licence text, licence identifier, or terms confirmation is recorded anywhere in the repository. `docs/DATA_CARD.md` defers to "Kaggle's official flow" without naming terms. |
| Raw SHA-256 | `BLOCKED` | No raw-file digest is recorded. `src/data/curation.py` *requires* `raw_file_sha256` in its curation record, so curation cannot even begin without it. |
| Historical split arrays | `BLOCKED` | `X_train/X_val/y_train/y_val` Parquet inputs named in `configs/historical_reference_demo_recipe.json` were not found; `candidate_identity_status` is `pending_independent_verification`. Historical holdout row identities were never retained (`docs/DATA_CARD.md`). |
| Evaluated-model linkage | `BLOCKED` | Bundle-to-locked-metrics linkage is **unverified and must not be claimed**. The recipe records `historical_component_linkage: "unverified"` and retains no evaluation partition. The negative is **not** asserted either: nothing shows the served components did or did not participate in the original run. |
| Historical metrics | `OBSERVED` / `HISTORICAL` | AP `0.8288`, ROC-AUC `0.9613`, precision `0.6966`, recall `0.8378` at threshold `0.53`; TP/FP/FN/TN `62/27/12/42,621`. Hash-locked and arithmetically self-consistent, but **locked observations, not freshly reproducible evidence** — they cannot be recomputed in this environment. |
| Historical held-out test | `OBSERVED` / `HISTORICAL` | Programmatically quarantined by `configs/historical_test_quarantine_anchor.json` (42,722 rows, 74 fraud, row-hash checksum `2aa4710d…`) and enforced by `src/data/historical_quarantine.py`. **It has already been historically observed and is therefore not human-blind.** Any result on it carries the canonical label *"programmatically quarantined but historically observed; not human-blind"* (§6.3), never a clean-holdout description. |
| Calibration decision | `BLOCKED` | Comparison code exists; **no calibration-decision artifact exists**. The served score is `raw_score`. |

**Consequence for this protocol: two execution lanes.** Every quantitative
outcome defined here is conditional on an approved corpus whose identity,
licence, and digest are recorded. There are exactly **two** permitted lanes, and
the lane is declared in the run manifest **before execution**, never chosen after
seeing a result. The historically used public corpus is **not** barred: an honest
reproducible reference rerun is allowed. What is barred is presenting such a
rerun as new or human-blind.

### Lane A — independently unseen approved corpus

A corpus that has **not** been observed by this project or its author. Required
before execution: source identity, licence identifier with retained terms, raw
SHA-256, schema validation, and raw row/class counts (§2.1).

- The full protocol applies unchanged.
- Its `final_test` result **may be described as held out**, and as blind, **only
  if the corpus is genuinely not historically observed** — a positive assertion
  by the operator, recorded in the run manifest, not an assumption inherited by
  default.
- Model, calibration, threshold, feature, and cost decisions are all permitted,
  within the partition boundaries of §3.

### Lane B — approved copy of the historically used public corpus

The same public corpus behind the locked 2026-06-24 observations, obtained
through its official channel and hashed. Required before execution: identical
§2.1 evidence, plus an explicit `lane: "B"` declaration.

- **A reproducible reference rerun is explicitly permitted.** Its purpose is
  reproducibility and method demonstration: showing that the declared pipeline,
  run end to end from a hashed raw file, produces a coherent and inspectable
  result.
- Its `final_test` result **must carry this label verbatim, everywhere it
  appears**: *"programmatically quarantined but historically observed; not
  human-blind."*
- It **may not** overwrite, replace, supersede, or be merged into any historical
  artifact. All Lane B output goes to new versioned paths (§8.6).
- It **may not** be used to tune anything against the locked historical test.
  The quarantine in §3.3 and §8.3 applies with full force: no feature, model,
  hyperparameter, calibration, threshold, or cost decision may be selected or
  revised using it.
- It **may not** be presented as fresh blind validation, as an independent
  holdout, or as confirmation that the historical numbers were correct. It is a
  reference rerun and is described as one.
- Where a Lane B figure and a locked historical figure differ, **both are
  published** with the difference stated plainly; the locked artifact is never
  edited to agree.

---

## 2 — Dataset and curation plan

### 2.1 Required before any execution

Record all of the following in a versioned run manifest
(`src/utils/run_manifest.py`, `run_manifest_version` `1`) with
`run_kind = "dataset_duplicate_curation"`:

1. **Source identity** — provider, dataset name, version/snapshot date, and the
   exact retrieval URL or documented retrieval procedure.
2. **Licence confirmation** — the licence identifier and a retained copy or
   permanent link of the terms, plus an explicit statement that the intended use
   (offline research and portfolio demonstration) is permitted. A licence that
   cannot be named is a stop condition.
3. **Raw SHA-256** of the exact file, recorded as `raw_file_sha256`.
4. **Operator approval** for any corpus claimed to be genuinely new, via
   `src/data/source_approval.py`, bound to `approved_file_sha256` equal to the
   raw digest and naming the reviewer. Historical curation must carry **no**
   new-source approval (enforced at `curation.py`).
5. **Row and class counts** of the raw file, before curation.
6. **Schema validation** — exactly the 30 ordered features `Time`, `V1`–`V28`,
   `Amount` plus `Class`; `float64` for all features and `int64` for `Class`, per
   the dtype contract already pinned in `configs/historical_test_quarantine_anchor.json`.
   Missing, extra, non-numeric, NaN, infinite, or negative `Time`/`Amount` values
   fail closed.

### 2.2 Deduplication — before splitting, never after

Curation runs on the **whole corpus before any partitioning**, using the
existing `src/data/curation.py` policy, which this protocol adopts unchanged:

- **Conflicting-label duplicates fail the run.** Feature vectors that appear more
  than once with more than one distinct `Class` raise `ValueError` and stop
  curation. There is no silent majority vote, no coin flip, and no drop.
- **Identical duplicates are removed deterministically.** `frame.duplicated(subset=feature_columns, keep="first")`
  retains the **first occurrence in stable source order** and removes the rest.
  Source order is the file's row order; no shuffle precedes curation, so the
  result is reproducible from the raw digest alone.
- **Removals are reported by class.** `CurationSummary` records `removed_rows`,
  `duplicate_groups`, `removed_legitimate`, and `removed_fraud`. All four are
  published in the curation record and the run manifest.
- **Curated output is fingerprinted** — `curated_file_sha256` plus a row-content
  fingerprint, both bound into the curation record and cross-checked by
  `load_curated_dataset` on every downstream read.

### 2.4 Deduplication trade-off, stated rather than glossed

Curation is a **pre-split stage, not a data partition**: it touches every row
once, before any role is assigned, and no label-mediated or model-mediated
information crosses a partition boundary.

It is **not** entirely free of global dependence, and this protocol will not
pretend otherwise. Because duplicates are resolved across the whole corpus,
which specific rows survive into `final_test` depends on the corpus-wide
duplicate structure — a row's retention can be decided by an identical row that
later lands in `training`. This is a deliberate, declared choice: the
alternative, splitting first and deduplicating within partitions, leaves
identical feature vectors on both sides of the boundary and inflates held-out
metrics far more seriously. The historical corpus is known to contain 1,081
duplicate rows whose original split overlap is unrecoverable, which is precisely
the failure mode being avoided. The trade-off is recorded here so a reviewer can
weigh it, and the curation record publishes the duplicate-group count needed to
judge its size.

### 2.3 Stop rule

Execution halts, with no partial artifact promoted, if the source identity,
licence, raw digest, schema, dtypes, or curation counts differ from what this
protocol and its run manifest declare. See §8.

---

## 3 — Partition and leakage boundaries

### 3.1 Seeds

| Purpose | Seed | Source |
|---|---:|---|
| Master project seed | `42` | `configs/config.yaml` `project.random_seed` |
| Stratified partitioning | `42` | `src/data/split_data.py` `RANDOM_STATE` |
| Model fitting (all four families) | `42` | passed explicitly to every estimator |
| Bootstrap resampling | `42` | `src/evaluation/statistical_metrics.py` `random_seed` default |

All seeds are fixed **in this document before execution**. Changing a seed after
seeing any result is a protocol deviation and must be reported as one.

### 3.2 Six disjoint roles

Curation is a stage (§2.2). The curated corpus is then partitioned once,
stratified on `Class`, into **five mutually exclusive row sets**:

| Role | Share | Purpose | May influence model/threshold/calibration choices? |
|---|---:|---|---|
| `training` | 55 % | Fit preprocessing, resampling/class weighting, and all four model families | Yes |
| `validation_threshold` | 12 % | Model selection **and** threshold selection | Yes |
| `calibration_fit` | 9 % | Fit Platt and isotonic calibrators only | Yes |
| `calibration_eval` | 9 % | Compare identity / Platt / isotonic and select one | Yes |
| `final_test` | 15 % | One frozen evaluation after every choice is locked | **No — never** |

The 15 % final-test share is deliberately chosen to match the historical test
proportion so partition sizes remain comparable; it is not tuned.

### 3.3 Enforced boundaries

- **Preprocessing is fitted on `training` only.** `fit_preprocessor(X_train)`
  (`src/preprocessing/preprocessors.py`); every other role receives `transform`
  only. `StandardScaler` on `Time` and `Amount`; `V1`–`V28` passthrough;
  `remainder="drop"`.
- **Resampling and class weighting are training-only.** This project uses **no**
  SMOTE, over-sampling, or under-sampling, and this protocol introduces none.
  Imbalance is handled by each family's standard in-estimator mechanism,
  computed from `training` labels only: XGBoost uses `scale_pos_weight`
  (`src/models/advanced_models.py:210`); Logistic Regression and Random Forest
  use `class_weight="balanced"`. These mechanisms are **not identical to one
  another** — they cannot be, since the estimators differ — so what is held
  constant is the *rule*: each model gets its family-standard imbalance handling,
  parameterised only from `training` labels, declared in advance in §4.2, and
  never tuned per model after seeing a result.
- **Calibrators are fitted on `calibration_fit` only** and compared on
  `calibration_eval` only. `compare_calibrators` raises `ValueError` on any
  row-ID overlap between the two, so this boundary is machine-enforced rather
  than merely documented.
- **The threshold is selected on `validation_threshold` only.**
- **`final_test` influences nothing.** No feature choice, model choice,
  hyperparameter, calibration method, threshold, cost assumption, or review
  capacity may be selected, tuned, or revised using it — not once, not
  "just to check".

### 3.4 Declared double-dip, and why it is accepted

`validation_threshold` carries **two** development decisions: champion-model
selection and threshold selection. That is mild double-dipping — the threshold
is chosen on the same rows that already favoured the model producing the scores,
so the validation operating point is optimistically biased relative to a fully
independent selection set.

It is accepted, declared, and bounded rather than hidden. The reasons: at this
prevalence a sixth partition would leave every development set too positive-poor
to support either decision; both decisions are *development* decisions that
never touch `final_test`; and the bias affects only the validation-reported
operating point, not the frozen test result, which is the number that carries the
claim. The validation operating point is therefore reported as
**development-optimistic** and is never presented as an unbiased estimate of
deployed performance.

### 3.5 Overlap verification, recorded

Before any fitting, and again before the final evaluation:

- Compute feature-only SHA-256 row identifiers with
  `fingerprint_rows()` (`src/data/split_data.py:152`).
- Run `assert_disjoint_split_rows()` across **every pair** of the five roles —
  ten pairs, not the three the current helper checks. Any non-empty intersection
  is a stop condition.
- Publish a per-role aggregate `row_hashes_sha256`, row count, and positive count
  in the run manifest.
- Verify that no `final_test` row hash appears in any other role, and that the
  five role row counts sum exactly to the curated row count.

---

## 4 — Fair baseline plan

### 4.1 Pre-registered baselines — those that actually exist

| Model | Constructor | Present at `501d8a6` |
|---|---|---|
| Dummy majority-class | `create_dummy_baseline()` → `DummyClassifier(strategy="most_frequent")` | `VERIFIED` — `src/models/baseline_models.py:30` |
| Logistic Regression | `create_logistic_regression_baseline()` | `VERIFIED` — `baseline_models.py:48` |
| Random Forest | `create_random_forest_baseline()` | `VERIFIED` — `baseline_models.py:70` |
| XGBoost | `src/models/advanced_models.py` | `VERIFIED` |

**A transparent rule-based baseline is absent.** No rule or heuristic baseline
exists anywhere in `src/`, `scripts/`, or `tests/`. **MT2 does not implement one,
does not claim one, and does not assume one.** Any future rule baseline requires
its own pre-registration amendment before it may be compared or reported.

### 4.2 Identical treatment, declared in advance

Every model in the comparison receives:

- **The same permitted feature inputs** — the 30 curated features, no more.
- **The same preprocessing boundary** — one preprocessor fitted on `training`,
  applied unchanged to all roles.
- **The same split roles** — identical row sets, verified by role row hashes.
- **The same metric set** (§6) computed by the same code path.
- **The same seed** (`42`).
- **A declared compute budget** — wall-clock seconds, core count, thread
  settings, and the hyperparameter-search budget (number of configurations and
  the search space) recorded per model. If budgets are deliberately unequal, the
  asymmetry is stated explicitly in the results and the weaker-budget model is
  never described as simply "worse".

### 4.3 Known asymmetry, disclosed now

`DummyClassifier(strategy="most_frequent")` emits no informative positive-class
score (`src/models/model_comparison.py:589`). Its average precision therefore
degenerates to the partition's positive prevalence and its ROC-AUC to `0.5`.
This is a property of the estimator, not a measurement artefact, and is reported
as such rather than presented as a competitive result.

---

## 5 — Calibration and threshold protocol

### 5.1 Calibration candidates and partitions

Exactly three candidates, compared by `compare_calibrators`
(`src/evaluation/calibration.py:153`): **identity** (no calibration),
**Platt/sigmoid**, and **isotonic**. Platt and isotonic are fitted on
`calibration_fit`; all three are scored on `calibration_eval`. The two
partitions are disjoint by construction and the function raises on overlap.
**The quarantined `final_test` is never passed to this function** — the
function's own docstring states this requirement.

### 5.2 Pre-declared selection rule

Selection order, fixed before seeing any number:

1. **Brier score** on `calibration_eval` — lower wins.
2. **Expected calibration error (ECE)**, 10 bins — lower wins, used only to break
   a Brier tie.
3. **Operational impact** — the §6 review-volume and illustrative-cost
   consequence at the selected threshold, used only if 1 and 2 both tie.
4. **Identity wins all remaining ties.**

**Minimum improvement rule — stated as an equation, not a description.**

Define, for each candidate method *c* ∈ {Platt, isotonic}, on `calibration_eval`:

```
improvement(c) = Brier(identity) - Brier(c)
```

Improvement is therefore **positive when the candidate is better** than identity,
since a lower Brier score is better. A candidate is eligible to win **only if
both** of the following hold:

1. `improvement(c) >= 0.005` — the point estimate clears the declared margin
   `minimum_brier_improvement = 0.005`; and
2. `CI_lower(improvement(c)) > 0` — the **lower bound** of the 95 % paired
   bootstrap confidence interval for `improvement(c)` (§6.2, `n_resamples = 2000`,
   `seed = 42`, percentile method, paired on resampled rows) is **strictly
   greater than zero**.

Condition 2 is one-sided by construction: an interval straddling or touching zero
fails it, so "the interval excludes zero" can never be satisfied by a candidate
that is merely *different* from identity rather than *better*.

If both candidates are eligible, the §5.2 order applies: lower Brier wins, then
lower ECE, then operational impact, then **identity wins all remaining ties**.
If neither candidate is eligible, **identity is retained** and the outcome is
recorded as *"no calibrator cleared the pre-registered margin"*.

**Statistical-power floor, declared in advance.** If `calibration_eval` contains
fewer than **40 positive rows**, no calibration method is eligible, identity is
selected automatically, and the result is recorded as *"insufficient positives to
select calibration"* rather than as a comparison outcome. At this dataset's
prevalence a 9 % partition is expected to hold roughly 40–45 positives, so this
floor may well bind. **That outcome is pre-committed, not a failure**: isotonic
regression on a few dozen positives overfits, and reporting "identity retained"
honestly is a valid pre-registered result.

### 5.3 The score-type rule

**A raw score remains a raw score unless calibration is selected by this
protocol.** If identity wins — including by the power floor above — then
`score_type` stays `raw_score`, `calibrated_probability` stays `null`, and the
output is **never** described as a probability, a fraud probability, a
likelihood, or a confidence. `ThresholdProvenance.calibrated` remains `false`.

### 5.4 Threshold selection — validation only

Selected on `validation_threshold` alone, using
`build_threshold_metrics_table` and `select_recall_target_threshold`
(`src/evaluation/threshold_tuning.py`).

**Pre-declared rule:** the **highest-precision threshold achieving recall ≥ 0.80**,
subject to the review-volume constraint below. Deterministic tie-breaks, in
order: higher recall, then lower illustrative total cost, then lower numeric
threshold.

**Pre-declared illustrative operating assumptions** (all `SYNTHETIC`, all
editable, none representing any real merchant):

| Assumption | Value | Note |
|---|---:|---|
| Review capacity | 100 reviews/day | Illustrative analyst capacity |
| Review cost | ₹83 per flagged row | Illustrative |
| Legitimate-customer friction | ₹830 per false positive | Illustrative |
| Missed-fraud loss | ₹8,300 per false negative | Illustrative |
| Chargeback handling | ₹4,150 per caught fraud | Illustrative residual |

If no threshold satisfies recall ≥ 0.80 within review capacity, the constraint
is reported as unsatisfiable and the highest-precision threshold meeting recall
≥ 0.80 without the capacity constraint is reported **alongside** its capacity
overrun. The constraint is never quietly relaxed.

These assumptions are **not Razorpay economics**, not a savings estimate, and not
evidence that any threshold is cost-optimal.

---

## 6 — Evaluation and uncertainty

### 6.1 Required outputs

For every model and every reported partition:

PR-AUC (average precision) · ROC-AUC · precision · recall · F1 · TP · FP · FN ·
TN · review volume (`TP + FP`) · false positives per day · illustrative scenario
cost with all components itemised.

**False positives per day** is reported in two explicitly distinguished forms,
never merged:

- *Dataset-intrinsic*: `FP` in the partition ÷ **2 days**, the source sample's
  documented span.
- *Illustrative merchant*: false-positive rate × a declared daily transaction
  volume, labelled `SYNTHETIC` with the volume stated inline.

### 6.2 Uncertainty — pre-declared method

- **Proportions** (precision, recall, specificity, FPR): **Wilson score
  intervals** at 95 %, via `classification_wilson_intervals`
  (`src/evaluation/statistical_metrics.py:74`). Wilson is chosen over bootstrap
  for these because it stays well-behaved at small positive counts, which this
  dataset guarantees.
- **Average precision and AP differences between models**: **stratified paired
  bootstrap**, via `paired_average_precision_difference`
  (`statistical_metrics.py:97`). **Fixed replicate count `n_resamples = 2000`;
  fixed `random_seed = 42`; confidence level 0.95; percentile interval.**
- **Rare-positive treatment**: resampling is **stratified** — positives and
  negatives are resampled separately with their counts preserved
  (`statistical_metrics.py:121-125`). No replicate can therefore contain zero
  positives, which would make AP undefined. This is a property of the existing
  implementation and is relied upon deliberately.
- **Paired design**: model comparisons resample **rows**, not models, and score
  every model on the identical resampled rows, so the interval reflects the
  paired difference rather than two independent samples.
- Every reported point estimate carries its interval. A difference whose interval
  includes zero is described as **not distinguishable**, never as a win.

### 6.3 The single frozen test invocation

`final_test` is evaluated **exactly once**, after — and only after — the curated
corpus, the five partitions, the preprocessor, all four fitted models, the
selected model, the calibration decision, the threshold, and every cost
assumption are frozen and hashed.

The invocation writes one versioned artifact and never overwrites an existing
one. Three cases, and only three:

**(a) A complete result was materialized and examined → no rerun, ever, under
this protocol.** Once a final-test metric exists and has been looked at, this
protocol is spent. Re-running against the same partition after seeing an outcome
is exactly the multiple-comparisons leak the pre-registration exists to prevent,
and no justification — "the seed was unlucky", "a library version changed", "we
only glanced at it" — reopens it. Examination includes any partial viewing of
the metric, not only formal reporting.

**(b) A run that failed before producing usable results → recordable as `void`.**
If execution aborts before a final-test metric is materialized — a crash, an
out-of-memory kill, a stop condition firing, a corrupt artifact, an interrupted
job — the attempt is recorded as `status: "void"` together with its failure
evidence: the failure mode, the stage reached, the timestamp, the input hashes,
and the log excerpt. A `void` run:

- **produces no publishable metric** and none may be quoted, estimated, or
  alluded to from it;
- **does not permit silent selection** — every void attempt is enumerated in the
  run manifest, so a reader can see how many attempts preceded the reported one
  and satisfy themselves that "void" was not used to discard an unwelcome result;
- is distinguishable from case (a) by evidence, not by assertion: if a final-test
  metric was materialized at any point, the run is (a) and cannot be relabelled
  `void`.

**(c) A post-freeze change to code, data, config, or any hash → the result is
invalidated and a new versioned protocol and run are required.** Not an informal
rerun, not an amendment appended to this document. The new run gets a new
protocol version identifier, a new run manifest, and new versioned output paths;
the invalidated result is retained and marked invalidated rather than deleted,
with the changed hash named.

**Honesty of the corpus, by lane.** Under **Lane A**, the result may be described
as held out and blind only if the operator has positively asserted in the run
manifest that the corpus is not historically observed. Under **Lane B** — and
under Lane A whenever that assertion cannot be made — the result carries the
verbatim label *"programmatically quarantined but historically observed; not
human-blind"* and is **not** promoted to clean-holdout evidence under any
wording, in any document, at any level of summary.

### 6.4 Negative results are published

If the champion does not beat Logistic Regression by a distinguishable margin;
if calibration is not selected; if no threshold meets recall ≥ 0.80 within
capacity; if illustrative cost is minimised by a threshold nobody would ship —
each is **published as the pre-registered outcome**. Weaker-than-hoped results
are reported with the same prominence as favourable ones. There is no
condition under which a result is withheld for being disappointing.

---

## 7 — Serving / evaluation parity

### 7.1 Machine-readable artifact schemas

Every artifact below is JSON, deterministic, versioned, and SHA-256 hashed. All
are `PROPOSED` until produced.

| Artifact | Required keys |
|---|---|
| **Run manifest** | `run_manifest_version`, `run_kind`, `evaluation_scope`, `inputs{path,sha256,size_bytes}`, `outputs{…}`, `parameters`, `seeds`, code provenance (commit SHA, dirty flag), runtime provenance (Python, package versions) — schema already implemented in `src/utils/run_manifest.py` |
| **Curation record** | `format_version`, `raw_file_sha256`, `curated_file_sha256`, `curated_fingerprint`, `duplicate_policy`, `source_approval_sha256`, `removed_rows`, `duplicate_groups`, `removed_legitimate`, `removed_fraud` |
| **Partition record** | per role: `row_count`, `positive_count`, `row_hashes_sha256`; plus the ten pairwise overlap results and the sum-check against the curated row count |
| **Metrics** | per model per partition: every §6.1 field, plus Wilson intervals, bootstrap AP intervals, `n_resamples`, `random_seed`, `confidence_level` |
| **Calibration** | per method: `brier_score`, `expected_calibration_error`, `n_bins`, reliability table; plus `selected_method`, `minimum_brier_improvement`, the CI for the Brier difference, `calibration_eval_positive_count`, and the power-floor verdict |
| **Threshold** | `value`, `source`, `rule`, `recall_target`, `review_capacity`, tie-breaks applied, and the full validation threshold table |
| **Cost assumptions** | every §5.4 value, its currency, and an explicit `illustrative: true` flag |
| **Bundle manifest** | bundle format `3` as implemented in `src/artifacts/bundle.py`: `model_version`, `score_type`, `operating_threshold`, `feature_schema`, `training_data_fingerprint`, `intended_use`, `threshold_provenance`, `training_provenance.data_roles{training,calibrator_fit,threshold_selection}`, quarantine provenance (`anchor_sha256`, `row_hashes_sha256`) |

### 7.2 The hash chain

An unbroken chain of SHA-256 links must connect, in order:

`raw file` → `curation record` → `curated file` → `partition row-hash set per
role` → `preprocessor artifact` → `model artifact` → `calibrator artifact (or an
explicit null)` → `threshold record` → `evaluation artifact` → `served bundle
manifest`.

Each link records the digest of the artifact it consumed. A break anywhere
invalidates every downstream claim. `ThresholdProvenance.model_linkage` must
name the exact model artifact digest, not a description.

### 7.3 Parity checks

On a **fixed set of rows declared in advance**, the following must agree within
tolerance:

- direct in-process scoring (`score_bundle_frame`),
- the single-prediction API endpoint,
- the batch API endpoint.

**Declared tolerance: absolute `1e-12`**, matching `GOLDEN_PROBE_TOLERANCE`
(`src/artifacts/bundle.py:50`). Any difference exceeding it is training-serving
skew and is a stop condition. The bundle's own golden probe
(`_golden_probe`, `bundle.py:1234`) must pass at load time in addition to these
row-level checks.

### 7.4 The linkage prohibition, restated

**The current historical-reference bundle must never be claimed to have
generated the historical metrics without independent linkage proof.** Such proof
requires the retained evaluation partition identities, the exact evaluated model
artifact digest, and a reproduction matching the locked values. None of the
three exists today. Absent them, the linkage stays `unverified` — and the
opposite is not asserted either.

---

## 8 — Stop conditions

Execution halts immediately, no partial artifact is promoted, and the condition
is reported. These are **not** warnings.

1. **Missing approved data, licence, or hash** — any of: absent raw file, unnamed
   or unconfirmed licence, missing `raw_file_sha256`, missing or mismatched
   operator approval, or a raw digest that differs from the pre-registered value.
2. **Partition overlap or duplicate-policy failure** — any non-empty intersection
   among the ten role pairs; role counts not summing to the curated row count;
   conflicting-label duplicates detected; or curation removal counts differing
   from the run manifest.
3. **Test-quarantine violation** — `final_test` rows reaching preprocessing fit,
   resampling, model fitting, calibration fit or evaluation, threshold selection,
   or any cost-assumption choice; a second evaluation of `final_test`; or any
   quarantine row hash appearing in another role.
4. **Calibration or threshold leakage** — calibrator fitted on anything other
   than `calibration_fit`; calibration compared on anything other than
   `calibration_eval`; overlap between the two; threshold selected on anything
   other than `validation_threshold`; or the selection rule altered after any
   number is seen.
5. **Non-deterministic artifact mismatch** — re-running a stage with identical
   inputs and seeds producing a different artifact digest; a deterministic export
   failing `--check`; or a run manifest whose recorded digests disagree with the
   files on disk.
6. **Any attempt to overwrite historical evidence** — writing to
   `reports/final/`, `reports/threshold_tuning/selected_thresholds.json`,
   `reports/model_comparison/`, `reports/operations/`, the quarantine anchor, or
   the historical observation lock. New evidence goes to **new versioned paths**.
   `verify_historical_observation.py` must still pass afterwards.

A deviation discovered *after* the fact is disclosed in the results with equal
prominence to the findings; it is never silently corrected.

### 8.7 Execution preconditions — MT3 remains locked until all three exist

Adding Lane B widens *which corpus* may be used. It does **not** lower the
evidence bar, and it does not unlock execution. **Both lanes require all three
of the following**, and MT3 stays locked until every one is available:

1. **An approved corpus** — the actual data file present locally, obtained
   through its official channel, with operator approval recorded per
   `src/data/source_approval.py`. Lane B needs an approved *copy* of the public
   corpus; conceptual familiarity with it is not a copy.
2. **Retained licence and terms** — a named licence identifier plus a retained
   copy or permanent link of the terms, and an explicit statement that the
   intended use is permitted.
3. **The raw SHA-256** — recorded as `raw_file_sha256`.

This is enforced by code, not merely by policy: `src/data/curation.py` requires
`raw_file_sha256` in its curation record and refuses to proceed without it, so
no amount of protocol interpretation can start execution while item 3 is absent.

At the time of writing, **all three are absent** (§1). The next action after this
protocol is accepted is therefore to **supply these data preconditions** — not to
begin MT3, and not to treat Lane B as a way around them.

---

## 9 — Claims this protocol does not authorise

Executing this protocol, whatever it yields, never licenses:

- live merchant, Razorpay production, RTO, or chargeback performance claims;
- describing any score as a probability, likelihood, or confidence unless
  calibration is selected under §5.2 and its artifact is published;
- semantic, causal, or business interpretations of the PCA components `V1`–`V28`,
  or causal readings of SHAP attributions — SHAP is non-causal, and protected-
  group fairness is unevaluable here because no protected attributes exist
  (missing evidence, not evidence of fairness);
- capacity, throughput, RPS, or SLO claims; every benchmark in this repository
  is single-run loopback;
- ACID, exactly-once, immutable or WORM audit, distributed durability, or
  crash-recovery claims — audit evidence is tamper-evident, not immutable, and
  idempotency is in-process and lost on restart;
- Vulcan access, use, parity, or superiority;
- ROI, cost savings, or "production-ready";
- autonomous approve, block, or decline behaviour;
- arm64 container support or a multi-architecture image;
- internship selection odds or probability of winning;
- bundle-to-locked-metrics linkage (§7.4).
