# SecureSwipe claim-to-evidence matrix

Every claim that may be spoken in the pitch or written in the submission form
must appear in this table and must map to a committed artifact, a named test, or
a measured report. A claim that is not in this table has not been cleared to be
made.

- **Working target of this document (MT1):** `501d8a6d7d2db48397b355aab592d6ea359ae277`
  on branch `codex/recovered-demo-bundle`, tree
  `3fe7bb8ced6c2cece3b96a00b1bec7919b14fef0`. **This commit is branch-local and
  is NOT on `main`.** It is one commit ahead of `origin/main`, zero behind;
  merge-base is `399a482`. The delta is documentation-only: `git diff
  399a482..501d8a6 -- api/ src/ web/ scripts/ tests/ configs/ reports/
  Dockerfile .github/` is empty, so all code, model, workflow, and artifact
  evidence is byte-identical across the two commits.
- **Released content (a different commit):** `main` at `399a482`, tree
  `41bdc41710234fb4edef1edccf167513a665aa55`. Application code, frontend, and
  workflows are unchanged from the CI-green tree `6e112b8b…` (`374e167`, PR
  head `4c712c7`).
- **Status of this document:** every row below carries an evidence status
  (`VERIFIED` / `OBSERVED` / `INFERRED` / `PROPOSED` / `BLOCKED`) and an
  evidence class (`CURRENT/MEASURED` / `HISTORICAL` / `SYNTHETIC` /
  `FUTURE/REFERENCE`). **CI confirmation attaches to `399a482` / `374e167`
  only.** GitHub Actions has not run on `501d8a6` — the `Quality`, `Security`,
  and `Container` workflows trigger on `pull_request` and `push` to `main`, and
  `501d8a6` is an unmerged branch commit. **CI status for `501d8a6` is
  `BLOCKED`, not passing** (see 7.10). The release freeze recorded at the end
  describes `374e167`, not this working target.
- **Scope of the word "clean":** throughout this document "clean" and "clean
  checkout" mean *tracked files only*. At MT3e verification the working
  directory additionally holds 328 untracked files: 287 foreign tooling files
  (`graphify-out/`, `.freebuff/`, `.obsidian/`, `game/`), 35 MT2/MT3 Lane A
  files, two pre-existing packaging work-in-progress files (see 7.1a), and four
  dashboard screenshots. The Obsidian application writes inside the working
  directory while work proceeds, so untracked-file mtimes may change without
  any repository command having run.

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

| 2.5 | Four model families were compared on the historical validation split: XGBoost AP `0.8129`, Random Forest `0.8125`, Logistic Regression `0.6275`, Dummy (majority-class) `0.0017`; champion `xgboost_baseline`. | `reports/model_comparison/validation_model_comparison.csv`; `src/models/baseline_models.py` (`create_dummy_baseline`, `create_logistic_regression_baseline`, `create_random_forest_baseline`); `src/models/advanced_models.py` | `VERIFIED` / `HISTORICAL`. Baseline registry and the committed CSV read at `501d8a6`; figures are on the 42,721-row validation split, never the held-out test |

**Must not be claimed:** that the locked metrics were produced by the bundle
currently served. **Bundle-to-locked-metrics linkage is unverified and must not
be claimed.** The served bundle's own recipe,
`configs/historical_reference_demo_recipe.json` (SHA-256
`55670d71abd7a52131fe58576de1771b2b381ba8cdd085f9e4c420dd9ba0c5dd`, recomputed
at `501d8a6`), records `historical_component_linkage: "unverified"`,
`candidate_identity_status: "pending_independent_verification"`, and
`post_quarantine_split_roles: "abolished_merged_fitting_pool_only_no_evaluation"`
— that is, the recipe retains **no evaluation partition** and supplies **no
verified linkage** from this bundle to the locked evaluation.

What that evidence does and does not support, stated precisely: it establishes
that the retained record provides **no basis on which the linkage could be
verified**. It does **not** establish the negative — the repository holds no
evidence that the served components did or did not participate in the original
evaluation, and the absence of a retained partition in a reconstruction recipe
is not proof about the historical run. Status: `VERIFIED` that the linkage is
**unverified and unclaimable**; the negative is **not** asserted. See 3.3.

**Baseline scope boundary:** a Dummy majority-class baseline **does exist** in
both code and committed historical evidence, contrary to any earlier note
claiming otherwise. A **transparent rule-based baseline is absent** — no
rule/heuristic baseline appears anywhere in `src/`, `scripts/`, or `tests/`.
Claim three baselines plus the champion, never "a rule baseline".

## 3 — Genuine model inference and provenance

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 3.1 | A real XGBoost estimator executes through the FastAPI service; inference is genuine, not mocked. | `artifacts/historical-reference-demo-v1/manifest.json` (local, intentionally gitignored); `api/`, `src/artifacts/bundle.py` | Manifest SHA-256 `e355834d…`, model `5ce63f1a…`, preprocessor `07d4a9f4…`; loader plus golden runtime probe accept a real `xgboost.sklearn.XGBClassifier` (ledger, Micro-tasks 1–3) |
| 3.2 | Direct-model, single-API, and batch-API outputs agree within a declared tolerance of absolute `1e-12`. | `tests/test_api.py` parity tests | Ledger, Micro-task 3 |
| 3.3 | The served bundle is historical-tainted, **not** decision-eligible, and its linkage to the locked metrics is **unverified and must not be claimed**. | Manifest flags `historical_taint=true`, `decision_eligible=false`, `historical_metrics_claimed=false`, `evaluation_performed=false`, surfaced in the API `provenance` block; recipe `historical_component_linkage: "unverified"` and `post_quarantine_split_roles: "abolished_merged_fitting_pool_only_no_evaluation"` | `VERIFIED` / `HISTORICAL`. Manifest flags observed in the container smoke response recorded at `374e167`; the recipe fields independently re-read at `501d8a6`. The recipe retains no evaluation partition and no verified linkage, so the claim is unsupported. **The negative is not asserted:** no evidence here shows the served components did or did not participate in the original evaluation |
| 3.4 | Responses carry request ID, model/bundle version, schema version, model score, threshold, bounded decision, and provenance. | `api/schemas.py` | Live container response this session contained every field |
| 3.5 | The served score is `raw_score` — a model score, **never** a calibrated fraud probability. | `score_type: "raw_score"`, `calibrated_probability: null`; recipe `threshold.calibrated: false` | `VERIFIED` / `HISTORICAL`. Observed in the live response and asserted by the container smoke assertion script; recipe field re-read at `501d8a6` |
| 3.6 | Calibration **comparison code** exists (identity / Platt / isotonic, fitted and evaluated on enforced-disjoint partitions, identity winning ties, calibration selected only above a declared Brier margin). | `src/evaluation/calibration.py` (`compare_calibrators`, `fit_calibrator`, `evaluate_calibration`); `tests/test_calibration.py` | `VERIFIED` / `CURRENT/MEASURED`. Source read at `501d8a6`; `compare_calibrators` raises on any row-ID overlap between the calibration-fit and calibration-evaluation partitions |
| 3.7 | **No calibration-decision artifact exists for the Lane B served bundle.** Nothing links that bundle to a completed calibration run or records a winning method for it. | absence of any Lane B Brier / ECE / reliability artifact under `reports/`; recipe `threshold.calibrated: false` | `BLOCKED`. The capability in 3.6 must never be reported as a calibration *result for Lane B*. Lane A's separate, non-serving development decision is recorded in 6A.3 |

**Must not be claimed for Lane B:** authenticated original source inputs,
reproduced training data, or any calibration outcome. Row 3.6 proves the
comparison is *implemented*; row 3.7 records that Lane B has no published
result. Do not say the served Lane B model "is calibrated", do not name a
winning Lane B method, and do not describe its served score as a probability.
Lane A's development-only result in §6A does not alter this. The four source Parquet inputs were not found;
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
| 5.1 | A fixed-input **loopback** run recorded 500/500 valid responses at concurrency 8 with 0 errors, 0 timeouts, 0 non-2xx: p50 44.63 ms, p95 80.37 ms, p99 308.48 ms, 169.35 successful req/s. | `reports/operations/2026-08-25_genuine_model_api_benchmark.md` and `.json` (SHA-256 `f4c9023e8d9b86595fbebdee4becf36f26762e5311a7142daa98d7f9ca2054ff`, recomputed at `501d8a6` — matches) | `VERIFIED` / `HISTORICAL`. **Code SHA `bc2fc8502f8479fbbc0b9f30a68d3eb1236df7d7` — neither `501d8a6` nor `399a482`.** One macOS 26.5.2 / arm64 Apple M2 Uvicorn worker, `127.0.0.1:18001`, `--workers 1`, no external network; **one repeat, one unmeasured warm-up**; harness `scripts/run_local_load_test.py`; evidence contract asserted by `tests/test_load_test.py` |
| 5.2 | Core model inference consumes **zero LLM tokens**. | `core_model_inference_llm_tokens: 0` in the benchmark JSON | Deterministic tabular XGBoost path; no LLM in the inference path |
| 5.3 | Cold start measured 5.85 s as an end-to-end **upper bound** including readiness polling and client startup. | Same report | Explicitly labeled an upper bound, not server-internal telemetry |
| 5.4 | The earlier logistic-regression run is synthetic serving-path plumbing evidence only. | `reports/operations/2026-08-24_local_single_node_serving_benchmark.md` | Labeled as such in README and ledger; never combined with 5.1 |
| 5.5 | On local loopback the serving path **does not scale with concurrency**: successful RPS stays in a flat ~73–81 band from 1 to 16 concurrent clients while p50 latency rises roughly linearly (12.4 → 24.3 → 49.4 → 96.9 → 189.7 ms baseline). 6,000 measured requests produced 0 non-2xx, 0 timeouts and 0 transport errors. | `docs/evidence/MT4_CONCURRENCY_EVIDENCE.md`; `docs/evidence/mt4/mt4_concurrency_benchmark.json`; protocol SHA-256 `5b2f13b42012efb5a8949a6a284e8d8e5b5dc6a3a8860cb8d7a047df0a63328d` | `VERIFIED` / `CURRENT/MEASURED`. **HISTORICAL-SERVING / NOT COMPARABLE TO MT3 HELD-OUT METRICS.** Pre-registered protocol, 5 concurrency levels × 3 repeats, fresh server and audit log per level, medians plus every per-repeat value published. Loopback only; not a production SLO and unrelated to fraud-detection quality |
| 5.6 | Removing the global inference lock **does not help** and was rejected: median RPS fell at four of five concurrency levels and p99 worsened at concurrency 2 (+52.1 %), 8 (+8.9 %) and 16 (+26.9 %). The shipped lock is retained. | `docs/evidence/MT4_CONCURRENCY_EVIDENCE.md` §5 | `VERIFIED` / `CURRENT/MEASURED`. A measured negative result against a pre-registered decision rule (≥20 % RPS gain or ≥20 % p99 cut, with no p99 worsening). Concurrent semantic parity was bit-exact first, so the rejection is on performance grounds, not correctness |
| 5.7 | The binding serving constraint is **audit append cost, not inference**: the writer re-verifies the whole hash chain before every append, so append latency grew from 0.895 ms (first 50 appends) to 12.518 ms (last 50) across 600 events — a 14× increase, linear per append and O(N²) overall. | `docs/evidence/MT4_CONCURRENCY_EVIDENCE.md` §6; `docs/evidence/mt4/mt4_audit_append_growth.json` | `VERIFIED` / `CURRENT/MEASURED`. This is a deliberate tamper-evidence property, not a defect; it trades sustained append throughput for detectability of out-of-band mutation. Reported as found, unfixed in MT4 |

**Must not be claimed:** 1,000 or 10,000 RPS, production capacity, an SLO,
public-network or multi-node results, or representative traffic. The p99 of
308.48 ms is disclosed rather than hidden. This measurement was taken on a dirty
worktree at code SHA `bc2fc850…`, before the release commit; it is **not** a
measurement of `501d8a6`, `399a482`, or `374e167`, and a single run with one
repeat supports no statistical claim. `reports/operations/local_m2_load_baseline.json`
records **no code SHA at all** and uses the `synthetic-smoke-1` model; it is
`SYNTHETIC` and unattributable to any commit. There is **no public-network
benchmark artifact in this repository**; every measured artifact is loopback.
Rows 5.5–5.7 supersede 5.1's single-run limitation with a pre-registered,
three-repeat matrix at a known commit, but remain loopback-only and carry the
`HISTORICAL-SERVING / NOT COMPARABLE TO MT3 HELD-OUT METRICS` label: they serve a
historical demo bundle, not the sealed Lane A model, and say nothing about
fraud-detection quality. Multi-worker serving remains **incompatible with current
state ownership** because idempotency, admission and audit state are process-local.

## 6 — Illustrative cost scenario

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 6.1 | The panel is a what-if calculator over the locked confusion-matrix counts with user-editable INR assumptions (review cost, legitimate-customer friction, missed-fraud loss, chargeback handling). | `web/components/IllustrativeCostScenario.tsx` | `web/__tests__/illustrative-cost-scenario.test.tsx`; `tests/test_cost_analysis.py` (8 tests incl. zero-cost, high-FP, high-FN, boundary) |
| 6.2 | The exact disclaimer "Illustrative scenario — not Razorpay economics and not a production-optimal threshold." is visibly displayed. | Dashboard | Visually confirmed this session at both 1280×800 and 375×812 |

**Must not be claimed:** real savings, Razorpay economics, ROI, or a
production-optimal threshold.

## 6A — Lane A v2 development evidence (separate from Lane B)

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 6A.1 | Lane A development protocol v2 is a post-v1 amendment motivated by observed feature limitations and the review-capacity conflict; it is not an untouched preregistration. | `docs/evidence/LANE_A_PROTOCOL_V2_AMENDMENT.md`; SHA-256 `f53bcb7df3a3187b840687e03b0b4d071c21a2936bd72cf46d991a5107591021` | `VERIFIED` / `CURRENT/MEASURED`. The amendment predates the first v2 superset and run manifest and its digest is embedded in the private aggregate run manifest |
| 6A.2 | Variant E (`full_candidate_snapshot`, 24 inputs) was selected on Lane A `validation_threshold`: AP `0.275929` versus baseline A `0.213582`, paired improvement `+0.062347`, 95% CI `[+0.051447, +0.073070]`; all predeclared gates passed. | `docs/evidence/LANE_A_V2_FREEZE.md`; private aggregate manifest digest `67aba752995e49537acae09befedde489aaf3937f3042e338321296a0c4ad410` | `VERIFIED` / `CURRENT/MEASURED`. Fixed XGBoost parameters, 2,000 stratified paired resamples, seed 42; deterministic rerun reproduced every AP and interval. This is development-optimistic, not final or deployed performance |
| 6A.3 | Platt passed the Lane A v2 gate on the previously reused `calibration_eval` role: Brier `0.029750` versus identity `0.100475`; improvement `+0.070724`, 95% CI `[+0.069460, +0.072052]`. “Calibrated probability” is permitted for this Lane A development output only. | `docs/evidence/LANE_A_V2_FREEZE.md`; calibration-decision digest `876db378c94d006f8d6381f9f5b9efca20cfc837bedfec92c969f802055239cf` | `VERIFIED` / `CURRENT/MEASURED`. Platt fitted on `calibration_fit` only; evaluated on `calibration_eval` only; isotonic was not reopened. The evaluation role was used in v1 and is not an untouched independent estimate |
| 6A.4 | Lane A's frozen operating policy is merchant-configured capacity → deterministic highest-score review allocation, not one universal threshold or capacity. | `src/lane_a/capacity.py`; `docs/evidence/LANE_A_V2_FREEZE.md`; policy-contract digest `6726d4262b84174bc1ed26aafbebbc84c8d512e568880f4f18adc460f45573c3` | `VERIFIED` / `CURRENT/MEASURED`. `review_budget=floor(daily_capacity×days)`; equal scores use stable private source order; only `below_review_threshold`, `human_review`, `unavailable_fail_closed` are emitted |
| 6A.5 | The five illustrative Lane A capacities expose a recall/workload trade-off: 100/day reaches recall `0.2935`; 1,000/day reaches `0.8115`; the derived 80% reference is 21,420 reviews (≈965/day), not a default. | `docs/evidence/LANE_A_V2_FREEZE.md`; aggregate frontier digest `2da03943d3ebbf6548c1326589b74bd76e9e77783aed976e323ab040355d7575`; `web/data/laneACapacity.ts` | `VERIFIED` / `CURRENT/MEASURED`. Aggregate arithmetic and frontend values reconcile exactly. Every tier is labelled illustrative, not Razorpay economics, not a production SLO, and not a universal policy |
| 6A.6 | The static Lane A workbench exposes aggregate development evidence and is visibly separate from Lane B historical evidence. | `web/components/dashboard/LaneACapacityWorkbench.tsx`; `web/__tests__/lane-a-capacity-workbench.test.tsx`; `web/app/page.tsx` | `VERIFIED` / `CURRENT/MEASURED`. Keyboard/unit, accessibility, production build and 375 px overflow checks are part of the MT3e verification record; no row, ID, domain, device string, amount, label, score or private path is exported |
| 6A.7 | Lane A `final_test` was **programmatically held out** through all development and **evaluated exactly once**: AP `0.208660`, 95% CI `[0.195700, 0.222711]`; ROC-AUC `0.814975`, 95% CI `[0.806402, 0.822899]`; Brier `0.030468`; log loss `0.124252`; ECE `0.003556` over 15 bins; 88,581 rows, 3,083 positives, prevalence `0.034804`. | `docs/evidence/LANE_A_FINAL_EVALUATION.md`; sealed private result manifest `65fd02bb26f7e2cec909840f41855fc4af7589028e7a59fda7b5d41cd401d20c`; freeze `154f69b54a286f428a5b2db9aed2a9ec7a83d4dd` | `VERIFIED` / `CURRENT/MEASURED`. Protocol `55ce3f19…` and boundary amendment `0c07c274…` were both hashed before the runner existed; scores were sealed before any label was loaded; lifecycle ran `PREPARED → STARTED → SEALED` exactly once. Not human-blind, not externally blind, not comparable with Lane B |
| 6A.8 | On `final_test` the five illustrative capacities give recall `0.2718` / `0.4570` / `0.6439` / `0.8018` / `0.9384` at 100 / 250 / 500 / 1,000 / 2,000 reviews/day, at precision `0.2723` / `0.1831` / `0.1290` / `0.0803` / `0.0470`. The retrospective 80%-recall reference is 30,459 reviews (≈990/day) at precision `0.0810`. | `docs/evidence/LANE_A_FINAL_EVALUATION.md`; capacity-policy digest `6726d4262b84174bc1ed26aafbebbc84c8d512e568880f4f18adc460f45573c3` | `VERIFIED` / `CURRENT/MEASURED`. Every tier reconciles exactly: `TP+FP` equals the selected review count, `TP+FN` equals total positives, all cells sum to the row count, and no tier exceeds its frozen budget. The 80% figure is a retrospective benchmark diagnostic, never a merchant default or production capacity |
| 6A.9 | The final result is modestly below the development estimate at the lower capacities and essentially unchanged at the highest, consistent with `validation_threshold` having been reused for selection and disclosed as optimistic. | `docs/evidence/LANE_A_V2_FREEZE.md` (development); `docs/evidence/LANE_A_FINAL_EVALUATION.md` (final) | `OBSERVED` / `CURRENT/MEASURED`. Development recall was `0.2935` / `0.4854` / `0.6563` / `0.8115` / `0.9382`; final is `0.2718` / `0.4570` / `0.6439` / `0.8018` / `0.9384`. Reported as found; nothing was tuned, refitted or reselected in response |

**Lane A claim boundary:** the final evaluation is complete, sealed, and was run
exactly once (6A.7); it may never be repeated, and no result below it may be
used to tune, refit or reselect anything. No Lane A result is production,
Razorpay, Indian, live-merchant, human-blind, externally blind, or comparable
with Lane B. No capacity is a merchant recommendation. The workbench prioritises
human review only and never approves, blocks, declines or steps up a payment.

## 7 — Engineering and security posture

| # | Claim that may be made | Evidence | Verified how |
|---|---|---|---|
| 7.1 | The full Python suite passes on a clean exact-HEAD checkout of `501d8a6`: **758 passed, 0 failed, 0 skipped**, exit 0. | `pytest` (canonical, unmodified; `pyproject` `testpaths=["tests"]`) | `VERIFIED` / `CURRENT/MEASURED`. Run against a `git archive 501d8a6` export whose 341 files were confirmed byte-identical to HEAD, in a directory outside the repository; 27.5 s; `.venv` Python 3.12.10 on macOS 26.5.2 / Apple M2. **Must always be stated together with 7.1a** |
| 7.1a | In the **current MT3e working directory**, the canonical `python -m pytest` **exits 1**: 967 collected, 966 passed, 1 failed. The MT3e/project suite excluding the one unrelated WIP test file is green: 961 passed. | two pre-existing untracked work-in-progress files, `scripts/package_recovered_demo_bundle.py` and `tests/test_package_recovered_demo_bundle.py` | `VERIFIED` / `CURRENT/MEASURED`. `testpaths` is a filesystem glob, not a Git query, so pytest collects untracked files in `tests/` exactly like tracked ones. The unrelated WIP contributes 6 tests, 5 passing; the failure remains `TypeError: ModelBundle.__init__() missing 3 required positional arguments: 'intended_use', 'threshold_provenance', 'training_provenance'` — the WIP targets an older bundle schema than tracked `src/artifacts/bundle.py`. It was preserved unchanged as required. **This is a property of the uncommitted working directory, not a defect in `501d8a6` or MT3e.** Never publish 7.1 without 7.1a, or 7.1a without 7.1 |
| 7.2 | Lint and types are clean at `501d8a6`: ruff 0 findings; mypy 0 issues over the 30 CI-listed critical source files plus the isolated reference-stage wrapper; all 150 Python files compile. | CI-equivalent commands | `VERIFIED` / `CURRENT/MEASURED`, with two **disclosed substitutions**: `python -m compileall` writes `__pycache__` inside the repository, so an in-memory `compile()` sweep was run instead (150/150 files, 0 syntax errors); `ruff check` was run with `--no-cache` and `mypy` with `--cache-dir` redirected outside the repository. These are read-only equivalents, **not the canonical commands** |
| 7.3 | Frontend unit, build, and e2e gates on the CI-pinned Node 22.13.1: eslint, `tsc --noEmit`, 23 vitest tests, production build, 5 Playwright/Chromium e2e tests. | `web/` | `BLOCKED` at `501d8a6`. This result is carried forward from the `e3580e4` / `374e167` runs and from CI on `399a482`; **it has not been reproduced against `501d8a6` in a clean `npm ci` checkout, and no such run's command or environment is recorded here.** Any restatement must name the clean exact-HEAD checkout, the `npm ci` install, and the actual `node --version`. The repository's existing `web/node_modules` must **not** be used as evidence: it was installed 2026-08-13, seven days before `web/package-lock.json` last changed (2026-08-20), so it is not a verified `npm ci` state |
| 7.4 | No secrets are present anywhere in full Git history. | TruffleHog 3.96.0 (CI-pinned), `--exclude-detectors=Lob` | 2,348 chunks / 4,860,758 bytes: **0 verified and 0 unverified secrets** |
| 7.5 | Dependencies are hash-locked and free of known vulnerabilities. | `requirements/*.lock`, `web/package-lock.json` | `VERIFIED` / `CURRENT/MEASURED` for the macOS locks: at `501d8a6`, `pip_audit` on `requirements/quality.lock` and `requirements/api.lock` both returned "No known vulnerabilities found"; `npm audit --audit-level=high` returned 0. `HISTORICAL` for the two **Linux** locks (`api-linux.lock`, `quality-linux.lock`), which CI audits and which were not re-run here |
| 7.6 | The container runs hardened: non-root uid 10001, no pip, read-only rootfs, all capabilities dropped, `no-new-privileges`. | `Dockerfile` | Verified in-container this session; `tests/test_container_contract.py` |
| 7.7 | The candidate image has no HIGH or CRITICAL vulnerabilities. | Trivy 0.70.0 with repo `.trivyignore.yaml` | **Exit 0, 0 HIGH/CRITICAL** on `linux/arm64` image `sha256:e894e688…`, whose `org.opencontainers.image.revision` label equals the candidate SHA |
| 7.8 | No raw data, model weights, or credentials are committed. | Candidate tree inspection | No `.joblib`/`.pkl`/`.parquet` payloads committed; only aggregate report CSVs. `web/.env.local` is untracked and gitignored |
| 7.9 | The container release target is declared as `linux/amd64`, the architecture CI is configured to build, smoke-test, scan, and produce an SBOM for. | `.github/workflows/container.yml`; `docs/CONTAINER.md` | `OBSERVED` / `CURRENT/MEASURED` **as configuration only**. The `Container` workflow matrix and the `Dockerfile` were read statically at `501d8a6` and declare `linux/amd64` only. **No image was built, no runtime smoke test was executed, no Trivy scan was run, and no SBOM was generated locally at `501d8a6`** — `trivy` and `syft` are not installed on the verification host. This row evidences the *declared configuration*, not an executed container pipeline. Executed container results belong to CI at `374e167` / `399a482` and to the local `e3580e4` arm64 run in 7.6/7.7 |
| 7.10 | GitHub Actions status for `501d8a6`. | — | `BLOCKED`. **No CI evidence exists for `501d8a6`.** The workflows trigger on `pull_request` and `push` to `main`; `501d8a6` is an unmerged branch commit. Independent verification was additionally impossible in this session: the unauthenticated GitHub API returned `API rate limit exceeded` for both `501d8a6` and `399a482`, and `gh` is not installed. **Do not write "CI passes" for `501d8a6`.** The green result recorded under "Release freeze status" belongs to `374e167` / `399a482` |
| 7.11 | The local Python environment used for rows 7.1, 7.2, and 7.5. | `.venv` | `OBSERVED`. `.venv` is **pre-existing and not proven byte-identical** to `requirements/quality.lock`; `python -m pip check` reports no broken requirements across 178 packages, but its `pytest` 9.1.1 and `mypy` 1.17.1 may differ from CI's hash-locked versions. Local green therefore does not entail CI green |
| 7.12 | Commit signature status. | `git log --format=%G?` | `BLOCKED`. `501d8a6` reports `N` (unsigned), and `gpg` is not installed on the verification host, so **no commit signature — including `399a482`'s — was cryptographically verified in this session** |

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
| 8.1 | There is **no** verified public deployment of this release candidate, and any prior static URL is not evidence for it. | `README.md` "Live Demo" | `VERIFIED` / `CURRENT/MEASURED`. Checked-in workflows perform no deployment |
| 8.4 | Deployment-to-SHA linkage. | live HTTP response headers | `BLOCKED`. `https://secure-swipe.vercel.app/` returned HTTP/2 200 with hardened headers (HSTS, `X-Frame-Options: DENY`, `nosniff`, CSP, Permissions-Policy) when probed read-only during MT0, **but exposes no commit SHA or build metadata**. Three distinct SHAs are in play — documented deployed frontend commit `943d021c4757ac4102615eb26ceca0cf476baa76` (shipped by local Vercel CLI with no GitHub connection, so no automatic linkage exists), `origin/main` `399a482`, and working target `501d8a6`. The response carried `age: 151165` (~42 h), bounding the cached artifact to no newer than ≈2026-08-24 16:27 UTC, which **predates both** `399a482` and `501d8a6`. Reachability is not linkage. **Do not claim the deployment corresponds to `501d8a6` or to any SHA**, and do not infer linkage from visual similarity |
| 8.2 | The static dashboard remains useful with the local API down. | Dashboard | Rendered this session with **no API running**: locked historical evidence displayed, zero console errors, no page-level horizontal overflow at 375px |
| 8.3 | A model/bundle rollback path is documented and gated on explicit owner approval. | `docs/OPERATIONS.md:203` | Read this session |

**Must not be claimed:** a live URL, uptime, or production traffic, unless and
until a deployment is actually performed and verified.

## Release freeze status

**Scope of this section: `374e167` / `399a482` only. It does not describe the
`501d8a6` working target of this document** — see 7.10.

**FROZEN (at `374e167`).** All three workflows are green on `main` at merge
commit `374e167`, whose tree `6e112b8babac3de06a63226e86eda3658fb7e54b` is
identical to the verified PR head `4c712c7`, so CI validated exactly this
content. This CI result was **recorded from GitHub at the time** and was
**not re-verified during MT1** — the unauthenticated API was rate-limited and
`gh` is unavailable, so its present status is `OBSERVED`/`HISTORICAL`, not
freshly confirmed.

| Workflow | Conclusion | Covers |
| --- | --- | --- |
| Quality | success | Python suite, ruff, both mypy targets, deterministic export/historical/monitoring verifiers, hash-locked Linux install, wheel build and inventory, pip-audit; frontend lint/typecheck/vitest/build/Playwright and npm audit |
| Security | success | TruffleHog over full history; CodeQL for `python` and `javascript-typescript` |
| Container | success | `linux/amd64` build, smoke, Trivy HIGH/CRITICAL scan, SPDX SBOM |

No new feature may be added on top of this commit. A claim of "CI green" is
supported **only** in this exact form: all three workflows pass on `main` at
`374e167`, with the container release target scoped to `linux/amd64`. It may
**not** be restated for `501d8a6`.

**Still not claimable:** arm64 container support or a multi-architecture image
(row 7.9 and its scope note); a public deployment, live URL, or deployment-to-SHA
linkage (8.1, 8.4); any link between the served bundle and the locked metrics —
which is **unverified and unclaimable** (3.3, §2); any calibration outcome or
description of the score as a probability (3.5–3.7); a transparent rule-based
baseline (§2 baseline scope boundary); CI status for `501d8a6` (7.10); any
verified commit signature (7.12); and any capacity, SLO, RPS, or savings figure
beyond the measured single-run loopback numbers (5.1, 6.2).

**Also never claimable, unchanged:** live merchant or Razorpay production
performance; internship selection odds or probability of winning; Vulcan access,
use, parity, or superiority; RPS/SLO extrapolation; immutable or WORM audit
storage; ACID, exactly-once, or distributed durability; ROI or cost savings;
"production-ready"; autonomous approve, block, or decline; and semantic or
causal interpretations of the PCA components `V1`–`V28` or of SHAP attributions.
