# P0.1 information architecture decision

Status: local draft for review; architecture and copy planning only.

Evidence inspected: the rendered composition in `web/app/page.tsx` and
`web/components/dashboard/CommandCenterDashboard.tsx`, all components they
render, `web/public/data/dashboard.json`, the Lane A TypeScript data modules,
the evidence documentation cited below, and the four existing screenshots in
`web/.visual-review/`. The screenshots show the current page as a dense,
technical single-page dashboard; some screenshot hero wording predates the
current source and is visual evidence, not copy authority.

## 1. Decision summary

- Make SecureSwipe's primary identity a defense-only payment-risk decision aid;
  keep “Razorpay AI Builder Internship · Track 2” as small project context, not
  as the brand or proof of an integration.
- Replace the ten-anchor single-page navigation with five routes: **Overview**,
  **Review Policy**, **Operations**, **Evidence**, and **Methodology**.
- Limit the homepage to five product-level sections: promise and boundary,
  review workflow, review-policy snapshot, evidence status, and trust/details.
- Put the human-review decision and the cost of false positives before model
  internals; the system never approves, blocks, declines, or steps up a payment.
- Preserve every current rendered panel. Move technical material to the route
  where a reviewer would seek it, consolidate only where a current component
  mixes concerns, and retain limitations next to the claims they qualify.
- Preserve four visibly distinct evidence classes: locked historical
  evaluation, genuine local/reference inference, synthetic plumbing or
  reliability evidence, and illustrative cost scenarios. Lane A sealed final
  evidence remains separately named and is never compared with Lane B history.
- Do not promote a metric, benchmark, inference result, or cost total without
  its provenance and limitation. The homepage summarizes; the named routes
  hold the inspectable source detail.

## 2. Current-state panel inventory

Counting rule: this inventory counts 22 rendered panels or technical sections.
It excludes `Navigation`, `Footer`, and non-semantic `DashboardSlot` instances
because they are page chrome or layout wrappers. It counts the two semantic
`DashboardSection` instances and the two separately rendered panels inside
`ScopeEvidencePanel`, and it includes `LaneACostExplorer` separately because it
is a substantive panel rendered inside `LaneACapacityWorkbench`.

| Current panel/component | Actual file path | Evidence category | Current problem | Final destination | Keep/move/consolidate/disclosure |
| ----------------------- | ---------------- | ----------------- | --------------- | ----------------- | -------------------------------- |
| `CommandOverview` | `web/components/dashboard/CommandOverview.tsx` | Mixed summary: locked historical plus boundary copy | A technical metrics board and six-step pipeline compete with the product promise; Buildathon context is visually primary. | `/` sections 1 and 5 | **Consolidate** into `ProductHero`, `EvidenceStatus`, and compact `TrustAndDetails`; keep Track 2 as small context. |
| Historical evaluation command board (`DashboardSection`) | `web/components/dashboard/CommandCenterDashboard.tsx` | Grouping for Lane B historical evidence | The grouping makes six technical panels the dominant homepage body. | `/evidence#lane-b-historical` | **Move/consolidate** as the Lane B historical evidence chapter; retain its already-observed/not-out-of-time disclosure. |
| `HistoricalDatasetPanel` | `web/components/dashboard/HistoricalDatasetPanel.tsx` | Locked historical evaluation (Lane B) | Dataset scale and imbalance are important context but dominate the first page. | `/evidence#historical-dataset` | **Move** intact; expose a short homepage evidence link. |
| `ConfusionMatrix` | `web/components/ConfusionMatrix.tsx` | Locked historical evaluation (Lane B) | “Legitimate → legitimate” and “Fraud → legitimate” can be read as payment authorization rather than below-threshold routing. | `/evidence#historical-confusion` | **Move**; replace outcome wording with review/below-review-threshold language while preserving all counts. |
| `ModelPerformance` | `web/components/ModelPerformance.tsx` | Locked historical test plus historical validation comparison | Model-selection detail is evidence, not a first-screen product task. | `/evidence#historical-performance` | **Move** intact with validation/test labels. |
| `ThresholdCards` | `web/components/ThresholdCards.tsx` | Historical validation analysis (Lane B) | A free threshold explorer can look like a current policy recommendation. | `/review-policy#historical-threshold-reference` | **Move** as an explicitly historical reference; never present `0.53` as a merchant default. |
| `CurveAnalysis` | `web/components/CurveAnalysis.tsx` | Historical validation analysis (Lane B) | Full-range PR/ROC detail is too technical for the homepage and is not final-test evidence. | `/evidence#validation-curves` | **Move** intact with the validation-only disclosure. |
| `ShapSection` | `web/components/ShapSection.tsx` | Historical explainability artifact (Lane B) | Anonymized PCA features and unverified output units limit reviewer meaning; prominence can imply causal explanation. | `/evidence#historical-explainability` | **Move** and retain the noncausal/output-unit disclosure. |
| `RiskScoreDemo` | `web/components/RiskScoreDemo.tsx` | Mixed: illustrative score rule plus genuine local/reference inference | Two evidence classes share one card; “genuine” can be mistaken for production or decision-eligible inference. | `/review-policy#decision-rule` and `/operations#reference-inference` | **Consolidate/split** into `ReviewDecisionRule` and `ReferenceInferenceCheck`; keep opt-in, fixed-input, provenance, and fail-closed states. |
| `ServingBenchmarkPanel` | `web/components/dashboard/ServingBenchmarkPanel.tsx` | Synthetic serving-path benchmark | A preliminary synthetic benchmark is visually adjacent to model evidence and can be read as production capacity. | `/operations#benchmarks` | **Move** with source SHA, environment, single-worker, loopback, preliminary, and non-production limits. |
| `CurrencyContextBar` | `web/components/dashboard/CurrencyContextBar.tsx` | Synthetic/illustrative display disclosure | A global-looking currency control can appear to assign currency to historical `Amount`. | `/operations#synthetic-plumbing` and beside each cost scenario | **Consolidate** into local `DisplayCurrencyDisclosure` instances; preserve fixed display-only conversion wording. |
| `SyntheticPlumbingSimulator` | `web/components/SyntheticPlumbingSimulator.tsx` | Synthetic plumbing test | “Real-time” overstates a fabricated in-browser demonstration and the large simulator dominates the product story. | `/operations#synthetic-plumbing` | **Move**; rename to “Interactive synthetic plumbing test.” |
| `IllustrativeCostScenario` | `web/components/IllustrativeCostScenario.tsx` | Illustrative cost scenario on locked Lane B counts | It can be confused with merchant economics or with the newer Lane A sealed explorer. | `/review-policy#lane-b-historical-scenario` | **Move** into a clearly secondary, Lane B historical-reference disclosure; preserve all visible assumptions and “no recommendation” wording. |
| `PipelineTimeline` | `web/components/PipelineTimeline.tsx` | Methodology/system-boundary explanation | Useful trust detail, but its pipeline depth is not a homepage task. | `/methodology#system-boundary` | **Move**; retain the offline/static/request-path distinction. |
| `Methodology` | `web/components/Methodology.tsx` | Historical methodology and limitations | Dense fitting/selection/evaluation detail is progressive disclosure. | `/methodology#evaluation-method` | **Move** intact; keep limitations adjacent. |
| `DataProvenance` | `web/components/DataProvenance.tsx` | Export and artifact provenance | The full manifest is evidence detail; “every displayed result” must remain bounded to the exported historical dashboard data. | `/methodology#data-provenance` | **Move** full manifest; use only a short provenance cue on `/`. |
| Architecture, methodology and audit trail (`DashboardSection`) | `web/components/dashboard/CommandCenterDashboard.tsx` | Methodology/system-boundary grouping | “Scalable reference” and “audit trail” are broader than the three panels actually rendered, while the section is buried in a single long page. | `/methodology` | **Consolidate** as the Methodology route introduction; name only implemented/current boundaries and label reference architecture as such. |
| Claims-boundary panel in `ScopeEvidencePanel` | `web/components/dashboard/ScopeEvidencePanel.tsx` | Limitations/disclosure | Essential limitations arrive near the bottom after many qualified claims. | `/` section 5 and `/evidence#limitations` | **Consolidate** the highest-risk limits on the homepage; retain the complete list on Evidence and beside affected claims. |
| Evidence-taxonomy panel in `ScopeEvidencePanel` | `web/components/dashboard/ScopeEvidencePanel.tsx` | All four evidence labels | The taxonomy arrives after the evidence it is needed to interpret. | `/` section 4 and `/evidence#taxonomy` | **Move/consolidate** a compact cue near the top; keep the complete legend on Evidence. |
| `GithubCTA` | `web/components/GithubCTA.tsx` | Repository/documentation access | “Explore the full ML system” is broad and architecture-focused rather than reviewer-focused. | `/` section 5 and site footer | **Consolidate** as “Inspect implementation and evidence,” linking to repository, report, and named routes. |
| `LaneACapacityWorkbench` | `web/components/dashboard/LaneACapacityWorkbench.tsx` | Lane A development evidence plus illustrative capacity selection | It is appended after the main dashboard, outside the information hierarchy; development results can be confused with the sealed final evaluation. | `/review-policy#capacity-frontier` | **Move** and lead with role (`validation_threshold`), development-optimistic status, and no-default boundary. |
| `LaneACostExplorer` | `web/components/dashboard/LaneACostExplorer.tsx` | Sealed Lane A final aggregate evidence plus illustrative arithmetic | A nested panel mixes measured counts with editable money assumptions; its distinction from the parent development frontier needs stronger hierarchy. | `/review-policy#sealed-final-cost-explorer` | **Move** as a separately headed panel; keep sealed counts and illustrative monetary inputs visibly distinct. |

No current rendered panel or technical section is deleted. Unrendered legacy components such
as `web/components/Hero.tsx` and `web/components/ProblemSection.tsx` are not part
of the panel count and do not supply approved copy.

## 3. Final route and navigation structure

| Route | Navigation label | Purpose | Primary audience | Key content |
| ----- | ---------------- | ------- | ---------------- | ----------- |
| `/` | Overview | Explain the product boundary and direct a reviewer to the right evidence in under one minute. | Buildathon reviewer, risk/product lead | Product hero, review-only flow, Lane A policy snapshot, evidence-status cue, limits and detail links. |
| `/review-policy` | Review Policy | Make capacity, threshold, false-positive workload, and illustrative costs inspectable without selecting a production policy. | Risk reviewer, operations/product lead | Review decision rule; Lane A development capacity frontier; sealed Lane A final counts and cost explorer; historical Lane B threshold and cost references. |
| `/operations` | Operations | Show what is actually executable or measured locally and how it fails safely. | Engineer, technical reviewer | Genuine local/reference inference check; synthetic plumbing simulator; local benchmarks; display-currency disclosure; operational boundaries. |
| `/evidence` | Evidence | Provide the complete evidence record and explicit category separation. | Scientific/ML reviewer, auditor | Evidence taxonomy; historical dataset; confusion matrix; model comparison; validation curves; SHAP; complete limitations and source links. |
| `/methodology` | Methodology | Explain how training, evaluation, export, and static presentation are separated. | ML engineer, auditor | Pipeline timeline; methodology; data provenance/export manifest; implementation/report links. |

**Primary navigation count: 5.** The repository link remains a utility/footer
action, not a sixth primary navigation link. In-page anchors may support long
detail routes but must not be repeated as primary navigation items.

## 4. Homepage structure

| Order | Section name | User question answered | Content retained | Content intentionally deferred |
| ----: | ------------ | ---------------------- | ---------------- | ------------------------------ |
| 1 | Product promise and boundary | What does SecureSwipe do, and what does it never do? | Name, one-sentence value proposition, “human review only,” static/reference status, small Track 2 context, primary actions to Review Policy and Evidence. | Historical KPI grid, pipeline internals, benchmark numbers, model names. |
| 2 | Bounded review workflow | How does a risk signal become a safe action? | Compact path: evidence/input → bounded score/result → below threshold or human review; no approve/block/decline action. | Synthetic event controls, API request/response detail, threshold sweep. |
| 3 | Review-policy snapshot | What operational trade-off can a reviewer inspect? | A compact Lane A sealed-final snapshot showing that more review capacity raises coverage and false-positive workload; link to the complete frontier and illustrative cost explorer. | Editable cost controls, every tier/table, Lane A development frontier, Lane B historical scenario. |
| 4 | Evidence status | Which evidence is measured, executable, synthetic, or illustrative? | Four-category legend, separate Lane A sealed-final badge, one conservative historical summary, and “inspect Evidence” action. | Full confusion counts, comparisons, curves, SHAP, provenance manifest, benchmark tables. |
| 5 | Trust, limitations, and details | What should I not infer, and where can I verify the work? | No live merchant/Razorpay integration, no real economics/savings, no production-scale claim, no autonomous payment action; links to Operations, Evidence, Methodology, and repository. | Full limitation list, artifact paths/digests, methodology timeline. |

**Homepage primary content section count: 5.** Navigation and footer are page
chrome and are not counted as content sections.

## 5. Simple wireframe

```text
┌ SecureSwipe ─ Overview | Review Policy | Operations | Evidence | Methodology ┐
│                                                                            │
│  1. PRODUCT PROMISE + BOUNDARY                                              │
│  Payment-risk signals for bounded human review                             │
│  [Review policy] [Inspect evidence]                                         │
│  Human review only · Static-first · Track 2 project context                │
│                                                                            │
│  2. BOUNDED REVIEW WORKFLOW                                                 │
│  evidence/input → bounded score/result → below threshold OR human review   │
│                                      (never approve/block/decline)          │
│                                                                            │
│  3. REVIEW-POLICY SNAPSHOT                                                  │
│  Sealed Lane A aggregate: coverage ↔ review workload ↔ false positives     │
│  [Inspect all capacity tiers and illustrative cost assumptions →]          │
│                                                                            │
│  4. EVIDENCE STATUS                                                        │
│  [Historical] [Genuine reference] [Synthetic] [Illustrative]               │
│  Lane A sealed final remains separate from Lane B historical evidence      │
│  [Open the complete evidence record →]                                     │
│                                                                            │
│  5. TRUST, LIMITATIONS + DETAILS                                            │
│  No live merchant use · no Razorpay integration · no real savings claim    │
│  Operations →  Evidence →  Methodology →  Repository                       │
└────────────────────────────────────────────────────────────────────────────┘
```

The progressive-disclosure path is: understand the boundary on `/`, inspect
the decision trade-off on `/review-policy`, then verify runtime evidence on
`/operations`, measurement detail on `/evidence`, or provenance on
`/methodology`.

## 6. Product copy outline

This is a hierarchy and claim contract, not final marketing prose.

| Copy element | Proposed wording or message | Evidence |
| ------------ | --------------------------- | -------- |
| Page title | **SecureSwipe — Human-review payment-risk decision support** | Defense-only and bounded outcomes: `README.md`, `docs/LIMITATIONS.md`, `api/schemas.py`, `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` rows 1.2–1.3. |
| Value proposition | **Inspect payment-risk signals, review-capacity trade-offs, and their evidence before a human decision.** | Human-review capacity and bounded decision behavior: `web/components/dashboard/LaneACapacityWorkbench.tsx`, `web/data/laneAFinalFrontier.ts`, `api/schemas.py`. |
| Review-only boundary | **SecureSwipe can route a result to human review or mark it below the review threshold. It does not approve, block, decline, capture, or authorize a payment.** | `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` rows 1.2–1.3; `docs/LIMITATIONS.md`; `web/data/laneAFinalFrontier.ts`. |
| Evidence-status sentence | **This site combines locked historical evaluation, an opt-in genuine local/reference inference check, synthetic plumbing and reliability tests, and illustrative cost arithmetic; each is labeled and must not be treated as another category.** | `web/components/dashboard/EvidenceLegend.tsx`, `web/components/EvidenceLabel.tsx`, `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` row 1.4. |
| Lane A final label | **Sealed final evaluation — Lane A / IEEE-CIS; evaluated exactly once; not Razorpay, live-merchant, or production performance.** | `docs/evidence/LANE_A_FINAL_EVALUATION.md` §§7–9; `web/data/laneAFinalFrontier.ts`. |
| Lane A development label | **Development evidence — `validation_threshold`; development-optimistic and not comparable with Lane B.** | `web/data/laneACapacity.ts`; `web/components/dashboard/LaneACapacityWorkbench.tsx`. |
| Lane B metric label | **Locked historical random-holdout result — already observed; not current, out-of-time, or production evidence.** | `reports/final/historical_observation.lock.json`, `web/public/data/dashboard.json`, `web/components/ConfusionMatrix.tsx`. |
| Genuine inference label | **Genuine local/reference bundle inference — historical-tainted, not decision-eligible, and not linked to the locked historical metrics.** | `configs/historical_reference_demo_recipe.json`; local ignored `artifacts/historical-reference-demo-v1/manifest.json`; `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` rows 3.1–3.5. |
| Synthetic label | **Synthetic plumbing/reliability evidence — fabricated inputs or local serving-path measurements, not fraud-performance evidence.** | `web/components/EvidenceLabel.tsx`; `web/data/syntheticFixture.ts`; `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` §§5 and 7. |
| Illustrative label | **Illustrative scenario — editable assumptions over aggregate counts; not merchant economics, savings, ROI, a default, or a recommendation.** | `docs/evidence/MT5_COST_EXPLORER_EVIDENCE.md`; `web/components/dashboard/LaneACostExplorer.tsx`; `web/components/IllustrativeCostScenario.tsx`. |
| False-positive definition | **A false positive is a legitimate transaction sent to human review; it is not automatically declined.** | `web/data/laneAFinalFrontier.ts`; `docs/evidence/MT5_COST_EXPLORER_EVIDENCE.md` §4. |
| Short disclosure | **Research and portfolio evidence only. No live merchant use, public backend, Razorpay integration, production capacity, or real savings is established.** | `docs/LIMITATIONS.md`, `docs/DEPLOYMENT.md`, `docs/ARCHITECTURE.md`, `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` §§5 and 8. |
| Buildathon context | **Built for Razorpay AI Builder Internship · Track 2: AI Risk Manager** — small eyebrow/about text only. | `README.md`; `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` row 1.1. This supports project context, not affiliation, deployment, integration, data, or economics. |

### Required wording replacements

| Inspected wording | Replacement | Reason and evidence |
| ----------------- | ----------- | ------------------- |
| Hero eyebrow “Razorpay AI Builder Internship · Track 2: AI Risk Manager” as the first brand line | “SecureSwipe · AI Risk Manager”; move the Buildathon sentence to small context text. | Avoid making Razorpay the product brand. No integration exists: `docs/LIMITATIONS.md` §Razorpay context adapter. |
| “Fraud decisions, made inspectable.” | “Payment-risk review, made inspectable.” | “Decision” can imply authorization; only review/below-threshold outputs are supported by `api/schemas.py`. |
| “Real-time plumbing demonstration” | “Interactive synthetic plumbing test” | The component uses fabricated in-browser events: `web/components/SyntheticPlumbingSimulator.tsx`, `web/data/syntheticFixture.ts`. |
| Confusion labels “Legitimate → legitimate” and “Fraud → legitimate” | “Legitimate → below review threshold” and “Fraud → below review threshold.” | Match the bounded vocabulary and avoid an approval implication: `api/schemas.py`, `web/components/ConfusionMatrix.tsx`. |
| “Preliminary local synthetic serving-path benchmark” without an immediately visible source identity | Keep the label and append the exact report commit/environment and “not production capacity.” | `reports/operations/2026-08-24_local_single_node_serving_benchmark.md`. |
| “Explore the full ML system” | “Inspect implementation and evidence.” | Narrower, verifiable action: `web/components/GithubCTA.tsx`, `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md`. |
| Metadata “Fraud Detection & Risk Analytics” | “Human-review payment-risk decision support.” | Align metadata with the bounded product posture in `docs/LIMITATIONS.md`. |

Do not use “live fraud prevention,” “production-ready,” “Razorpay-scale,” “real
merchant savings,” “optimized policy,” or “deployed model.” Each **requires
evidence before use**: a reviewed live deployment and source linkage,
representative traffic and outcomes, an approved economics study, and/or a
domain-approved policy artifact do not exist in the inspected evidence.

## 7. Immutable-data list

The redesign may change hierarchy and presentation, but must not mutate,
reinterpret, recompute, or describe the following as newly measured.

| Immutable item | Source of truth and constraint |
| -------------- | ------------------------------ |
| Lane B locked historical metrics and confusion counts | `reports/final/final_model_evaluation.json` and `reports/final/historical_observation.lock.json`; the exported values in `web/public/data/dashboard.json` include threshold `0.53`, TP/FP/FN/TN `62/27/12/42621`, and the recorded metrics. Preserve exact values and historical-only status. |
| Lane B threshold and provenance | `reports/threshold_tuning/selected_thresholds.json`, `reports/threshold_tuning/threshold_metrics.csv`, `web/public/data/dashboard.json`; selected on historical validation under the recorded recall-target rule, not a merchant default or production recommendation. |
| Lane B dataset, split, comparison, curves, and SHAP artifacts | `reports/day2_eda_summary.md`, `reports/day3_preprocessing_summary.md`, `reports/model_comparison/`, `reports/threshold_tuning/`, `reports/figures/`, `reports/explainability/`; preserve validation/test distinctions, dataset limitations, and noncausal/unverified-output-unit SHAP language. |
| Historical observation integrity | `reports/final/historical_observation.lock.json` and `scripts/verify_historical_observation.py`; presentation must consume verified locked evidence and must not silently regenerate or retune it. |
| Lane A development capacity frontier | `web/data/laneACapacity.ts`, `docs/evidence/LANE_A_V2_FREEZE.md`; keep `validation_threshold`, development-optimistic, capacity-illustrative, and not-comparable-with-Lane-B labels. |
| Lane A sealed final result | `docs/evidence/LANE_A_FINAL_EVALUATION.md` and `web/data/laneAFinalFrontier.ts`; one-time `final_test` evaluation, result-manifest SHA-256 `65fd02bb26f7e2cec909840f41855fc4af7589028e7a59fda7b5d41cd401d20c`, fixed metrics/counts/tier order, and prohibited-claim boundary. |
| Lane A illustrative cost model | `docs/evidence/MT5_COST_EXPLORER_CONTRACT.md`, `docs/evidence/MT5_COST_EXPLORER_EVIDENCE.md`, `web/lib/laneACostModel.ts`; preserve the formula, visible editable assumptions, exact aggregate counts, fixed-point arithmetic, no winner/default, and no savings/ROI claim. |
| Reference bundle identity and limitations | Tracked recipe `configs/historical_reference_demo_recipe.json`; local ignored `artifacts/historical-reference-demo-v1/manifest.json`; `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` §3. Keep historical taint, `decision_eligible=false`, `historical_metrics_claimed=false`, raw-score semantics, and unverified linkage. Never imply this bundle produced the locked Lane B metrics. |
| Sealed-model/reference-model separation | `docs/ARCHITECTURE.md` §Current system shape and `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` §§3 and 6A; the sealed Lane A model is not the locally served historical-reference bundle. |
| Public dashboard export | `web/public/data/dashboard.json`, `web/data/metrics.ts`, and `scripts/export_web_data.py`; preserve schema version, source digest, artifact timestamp, source list, aggregate-only boundary, and deterministic check. Do not hand-edit measured values for the redesign. |
| Evidence vocabulary and decision vocabulary | `web/components/EvidenceLabel.tsx`, `web/components/dashboard/EvidenceLegend.tsx`, `api/schemas.py`, and `api/service.py`; keep the four user-facing classes distinct and outcomes bounded to human review, below-review-threshold, or unavailable/fail-closed states. |
| Synthetic fixtures | `web/data/syntheticFixture.ts` and `web/__tests__/synthetic-plumbing-simulator.test.tsx`; they remain fabricated plumbing/test inputs and never become model-quality evidence. |
| Frontend cost/capacity fixtures and assertions | `web/__tests__/illustrative-cost-scenario.test.tsx`, `web/__tests__/lane-a-capacity-workbench.test.tsx`, `web/__tests__/lane-a-cost-model.test.tsx`, `web/__tests__/lane-a-cost-explorer.test.tsx`; do not change expected evidence values merely to fit a layout. |
| Synthetic serving benchmark | `reports/operations/2026-08-24_local_single_node_serving_benchmark.md`; source commit `5a8b653e939bf77d71cea6ce3f99667449fa4ad3`, Apple M2/macOS/Python 3.12.10, one local worker, fixed synthetic bundle, 500-request run, and preliminary/non-production boundary travel with the figures. |
| Genuine-reference serving benchmark | `reports/operations/2026-08-25_genuine_model_api_benchmark.md` and its JSON evidence; code SHA `bc2fc8502f8479fbbc0b9f30a68d3eb1236df7d7`, disclosed dirty state, Apple M2, one worker, one repeat, fixed input, local loopback, historical-serving/not-quality boundary. It is not interchangeable with the synthetic benchmark or current HEAD. |
| Limitations and claim ledger | `docs/LIMITATIONS.md`, `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md`, `docs/DEPLOYMENT.md`, `docs/ARCHITECTURE.md`; route moves must not detach these qualifications from the claims they govern. |
| Existing visual baselines | `web/.visual-review/desktop-overview.png`, `desktop-synthetic-flow.png`, `mobile-overview.png`, and `mobile-synthetic-flow.png`; use as current-state comparison only, not as authoritative copy or evidence of a current deployment. |

## 8. Implementation sequence after approval

Do not begin any step until this architecture is reviewed and approved.

1. **Source changes — route shell.** Add the five routes and shared five-link
   navigation, with stable page headings, skip links, active-route semantics,
   metadata, and no change to evidence values. Review this as a route-only
   change.
2. **Source changes — homepage.** Build the five homepage sections using summary
   views over existing data. Confirm the review-only boundary and evidence cue
   before relocating detailed panels.
3. **Source changes — progressive disclosure.** Move/consolidate all 22 inventoried
   panels/sections according to the mapping above. Split `RiskScoreDemo` by concern and
   localize the currency disclosure; preserve behavior and evidence labels.
4. **Data/export changes.** Prefer no measured-data change. If new summary fields
   are genuinely needed, change the exporter/source schema in a separate review,
   regenerate deterministically, cite the upstream artifact, and never hand-edit
   `web/public/data/dashboard.json`.
5. **Test changes.** Update route/navigation assertions, preserve all numerical
   and claim-boundary tests, and add tests that every route exposes the correct
   evidence label, bounded vocabulary, opt-in inference, and mobile navigation.
6. **Visual verification.** Capture fresh desktop and mobile views for the
   homepage and each detail route; check the 30–60 second hierarchy, keyboard
   order, overflow, focus targets, and accessibility. Keep old screenshots as
   before-state evidence until review accepts the replacements.
7. **Claim-safety verification.** Run the deterministic export/historical
   verifiers and claim-language searches; review the rendered copy against
   `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md`, `docs/LIMITATIONS.md`, and the
   exact benchmark reports before approving any deployment.

## 9. Acceptance checklist

- [x] Homepage has five or fewer primary sections (exactly five).
- [x] Navigation has five or fewer links (exactly five).
- [x] Every current technical panel/section has a named destination (22 of 22).
- [x] No technical evidence is silently deleted.
- [x] Product copy makes no unsupported live-performance claim.
- [x] Historical, reference, synthetic, and illustrative evidence remain distinct.
- [x] No application source/configuration/data artifact was modified by P0.1-IA.
- [x] No commit, push, or deployment occurred during P0.1-IA.
