# SecureSwipe submission claim ledger — Block 1 truth freeze

## Freeze identity

| Item | Frozen observation |
| --- | --- |
| Freeze timestamp | `2026-09-02T15:53:18Z` (`2026-09-02 21:23:18 IST`) |
| Inspected working-tree commit | `b97193b88261105efc8ac21cd7cec202113ab7a4` on `codex/p1-core-checkpoint` |
| Local `origin/main` | `eb729a9cc11646e84737703b911c9d333d955be9` |
| Remote `refs/heads/main` | `eb729a9cc11646e84737703b911c9d333d955be9`, independently confirmed with `git ls-remote` during this freeze |
| Merge base | `8f8e36955c1d7b0ca4ee233ac4864d5fcc6428b9` |
| Divergence | Working branch is 41 commits ahead of and 65 commits behind `origin/main` |
| Worktree at inspection start | **Dirty**: 23 modified tracked entries, 13 untracked entries, no staged changes |
| Inspected `origin/main` tree | `01b76443c68169d09e7977454c0ae3fe063e18b5` |
| Inspected `origin/main:web` tree | `966236b56a433e1da7cacba148a2d5f05fdcb1ae` |

This ledger is the only file created by Block 1. Every other dirty or untracked
path listed below pre-dated the freeze and was inspected without staging,
resetting, stashing, cleaning, moving, renaming, or editing it.

### Concise repository state before the ledger was created

```text
 M .gitignore
 M README.md
 M tests/test_p1_s2_postgres_integration.py
 M web/AGENTS.md
 M web/__tests__/deterministic-demo.test.tsx
 M web/__tests__/route-split.test.tsx
 M web/app/demo/page.tsx
 M web/app/evidence/page.tsx
 M web/app/globals.css
 M web/components/EvidenceLabel.tsx
 M web/components/GithubCTA.tsx
 M web/components/Navigation.tsx
 M web/components/ThresholdCards.tsx
 M web/components/dashboard/ScopeEvidencePanel.tsx
 M web/components/demo/DeterministicJudgeDemo.tsx
 M web/components/product/BoundedReviewWorkflow.tsx
 M web/components/product/ProductHero.tsx
 M web/components/product/ProductHomepage.tsx
 M web/components/product/TrustAndDetails.tsx
 M web/e2e/dashboard.spec.ts
 M web/e2e/demo.spec.ts
 M web/lib/deterministic-demo.ts
 M web/next.config.ts
?? .github/ISSUE_TEMPLATE/
?? SecureSwipe diagrams/
?? docs/DIAGRAM_BLUEPRINT_DRAFTS.md
?? scripts/package_recovered_demo_bundle.py
?? secureswipe-methodology.html
?? tests/test_package_recovered_demo_bundle.py
?? web/__tests__/dashboard-redesign.test.tsx
?? web/components/evidence/ReliabilityEvidencePanel.tsx
?? web/components/product/DecisionWorkspacePreview.tsx
?? web/components/product/EvidenceKpiStrip.tsx
?? web/components/system/
?? web/e2e/visual-qa.spec.ts
?? web/lib/demo-journey.ts
```

### Recent commit truth

Current working branch:

```text
b97193b docs(scale): record P1-S4 terminal closeout evidence
2928829 test(scale): add rule-A classification mode to the postfix runner
5416305 test(scale): preserve evidence when a post-measurement gate fails
1227231 docs(scale): preregister P1-S4 terminal closeout protocol
8951e1a docs(scale): record P1-S4f state-store verification
```

Current `origin/main`:

```text
eb729a9 Merge pull request #21 from imayankss/codex/fix-dashboard-interactions-and-polish
0e2aa3d chore(web): update browserslist security dependencies
3df90f4 feat(web): polish dashboard and publish methodology
6d3dbf7 Merge pull request #20 from imayankss/codex/commit-deterministic-demo-controls
6376561 feat(demo): add recorded reference and rejected-request controls
303f065 feat: integrate SecureSwipe P1 product, evidence, and demo experience
```

## Repository, deployment, and link truth

### Public deployment

The current public frontend is verifiably linked to `origin/main`:

| Item | Verified value |
| --- | --- |
| Public URL | `https://secure-swipe.vercel.app` |
| Vercel project | `secure-swipe` |
| Vercel project ID | `prj_BXdOCyOKRpZzMuY7X7j0M1yrmtoV` |
| Production deployment ID | `dpl_9Jx19BdfNeE9PvGtZN3XgWpwRCpz` |
| Immutable deployment URL | `https://secure-swipe-nk5ne4asf-mayankssss27-gmailcoms-projects.vercel.app` |
| Provider-reported source SHA | `eb729a9cc11646e84737703b911c9d333d955be9` |
| Provider-reported source root | `web` |
| Deployment source | Vercel CLI |
| State | `READY`, target `production`, alias `secure-swipe.vercel.app` |

The source linkage is not inferred from appearance. The authenticated read-only
Vercel deployment record reports `meta.gitCommitSha=eb729a9...`,
`meta.gitRootDirectory=web`, the project ID above, and the production alias.
During the freeze, `/`, `/evidence`, `/demo`, and
`/secureswipe-methodology.html` each returned HTTP 200. Fetched public HTML
contained the sealed Lane A `80.18%` and `88,581` figures, the methodology
link, the `Run the 2-minute demo` call to action, and the `/demo` controls
`Run recorded reference` and `Test rejected request`.

The public CSP contains no configured external API origin. Consequently the
deployed `/demo` must be described as a static frontend with a clearly labelled
recorded reference transcript; live inference requires a separately configured
local reference API. There is no verified public scoring backend.

### Link agreement audit

| Surface | Current statement/link | Agreement verdict |
| --- | --- | --- |
| `origin/main` README | Gives local dashboard/demo instructions; says a verified pitch-video link is unavailable; says no public dashboard is presented as current | **Stale/disagrees** with the verified production deployment above |
| Dirty working-tree README | Still gives local UI/demo links, contains a dashboard-media placeholder, and provides no current production or video link | **Incomplete**; it also links an untracked architecture SVG, so that draft cannot be published alone |
| `docs/DEPLOYMENT.md` | Says deployed SHA is not independently verifiable and does not assert a current public URL | **Stale/disagrees** with the provider metadata now available |
| `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` | Uses old working/release SHAs and says deployment linkage is blocked | **Stale**; identities and deployment row must be superseded in Block 2 |
| `docs/evidence/SUBMISSION_PACKAGE.md` | Says no verified deployment; foregrounds Lane B metrics and old test counts | **Stale and submission-blocking** |
| `docs/evidence/MT9_RELEASE_FREEZE.md` | Correctly records an older checkpoint as not deployed/current | **Historical only**; preserve, do not rewrite as current |
| Live footer | `/secureswipe-methodology.html` | **Agrees** with the file committed at `web/public/secureswipe-methodology.html`; HTTP 200 |
| Live repository CTA | `https://github.com/imayankss/SecureSwipe` | **Agrees** with the configured repository and clone URL |
| Pitch video | No verified external video URL found in README, submission package, or website configuration | **Missing**; no video claim is authorized |

### Current CI observation for `origin/main`

The public GitHub check record for `eb729a9...` has five completed checks:
frontend **success**, `linux/amd64` build-smoke-scan **success**, secrets
**success**, CodeQL **success**, and Python **failure**. The Python job failed in
its `Test` step; later export, verifier, audit, and wheel steps were skipped.
Unauthenticated GitHub access did not expose the private job log, so this freeze
does not guess at the failing test. It is not permissible to say that all CI is
green on the current deployment SHA.

## Submission claim ledger

The five model/evidence categories are intentionally kept separate. Rows marked
`administrative identity` are repository or deployment facts, not model
evidence, and inherit no metric claim.

| ID | Likely public surfaces | Evidence category | Exact evidence/artifact | Safe wording | Prohibited wording |
| --- | --- | --- | --- | --- | --- |
| C01 | README, dashboard, video, form | administrative identity | `README.md`; `web/components/dashboard/CommandOverview.tsx` | “Built for Razorpay AI Buildathon 2026, Track 02 — AI Risk Manager.” | Razorpay affiliation, endorsement, deployment, integration, customer use, or winning/selection probability |
| C02 | All | sealed Lane A | `docs/LIMITATIONS.md`; `docs/MODEL_CARD.md`; bounded decision types in `api/schemas.py` and UI | “Defense-only decision support that routes a bounded signal to human review or below-threshold handling; payment authority remains outside SecureSwipe.” | Autonomous approval, allow, block, decline, capture, settlement, or payment action |
| C03 | README, dashboard, video, form | sealed Lane A | `docs/evidence/LANE_A_FINAL_EVALUATION.md` §§1–3 | “One programmatically held-out IEEE-CIS Lane A evaluation, run exactly once: 88,581 rows, 3,083 positives, prevalence 3.4804%, AP 0.208660 (95% CI 0.195700–0.222711), ROC-AUC 0.814975 (95% CI 0.806402–0.822899).” | Razorpay, Indian-payment, live-merchant, future, universal, human-blind, externally blind, or production performance |
| C04 | README, evidence dashboard, video, form | sealed Lane A | `docs/evidence/LANE_A_FINAL_EVALUATION.md` §3 | “Lane A also recorded Brier 0.030468, log loss 0.124252, and descriptive 15-bin ECE 0.003556.” | A guarantee of calibration under shift, or describing any model score as a real-world fraud probability |
| C05 | README, dashboard, video, form | sealed Lane A | `docs/evidence/LANE_A_FINAL_EVALUATION.md` §5; `web/data/laneAFinalFrontier.ts` | “At the illustrative 1,000-reviews/day tier, recall was 80.18% and alert precision 8.03%; TP/FP/FN/TN were 2,472/28,306/611/57,192.” | Recommended/default capacity, staffing level, SLO, fraud prevented, automatic rejection, or forecast |
| C06 | README, dashboard, video | sealed Lane A | `docs/evidence/LANE_A_FINAL_EVALUATION.md` §§5–6 | “Across the five frozen illustrative tiers, higher review capacity raises recall and also raises legitimate reviews; no tier is selected as optimal.” | “Best” threshold/capacity, guaranteed 80% recall, or production policy |
| C07 | README, evidence dashboard, video | sealed Lane A | `docs/evidence/LANE_A_FINAL_EVALUATION.md` §§1, 7–9; `docs/evidence/LANE_A_FINAL_EVALUATION_PROTOCOL.md` | “Scores were sealed before final labels were opened; the final result is closed and cannot be reused for tuning or rerun.” | Independent blindness, external audit, repeated trial, or a right to reopen/tune on `final_test` |
| C08 | README, dashboard, model card | sealed Lane A | `docs/MODEL_CARD.md`; `docs/LIMITATIONS.md`; `docs/EVIDENCE_GUIDE.md` §P0.4 | “Lane A variant E is a frozen 24-input XGBoost pipeline with Platt calibration, but its exact serving chain is unavailable or cryptographically unproven.” | That `/demo`, the local API, or any retained reference bundle serves the sealed Lane A model |
| C09 | Evidence dashboard, supporting video/form only | historical | `reports/final/final_model_evaluation.json`; `reports/final/historical_observation.lock.json`; `scripts/verify_historical_observation.py` | “Separate Lane B historical random-holdout record: threshold 0.53; AP 0.8288; ROC-AUC 0.9613; precision 69.66%; recall 83.78%; 42,722 rows.” | Headline/current result; comparison or superiority over Lane A; temporal/live result; attribution to the served bundle |
| C10 | Evidence dashboard, model card | historical | `configs/historical_reference_demo_recipe.json`; `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md` §§2–3 | “Bundle-to-Lane B-metrics linkage is unverified and must not be claimed.” | That evidence proves the retained bundle did or did not produce the historical metrics |
| C11 | `/demo`, README, video | reference demo | `web/app/demo/page.tsx`; `docs/MODEL_CARD.md`; `docs/REPRODUCIBILITY.md` | “`/demo` is a separate local reference-model walkthrough using a fixed sanitized synthetic fixture when a verified local API is configured.” | Lane A demonstration, real transaction, live merchant inference, or public scoring service |
| C12 | Public `/demo`, video | reference demo | `web/lib/deterministic-demo.ts` (`RECORDED_REFERENCE_RUN`); `web/__tests__/dashboard-redesign.test.tsx` | “The public `Run recorded reference` path replays a repository-stored transcript and is not measured now.” | Live inference, a newly generated result, present API availability, or proof of current audit append/replay |
| C13 | Local `/demo`, API documentation, video | reference demo | `api/main.py`; `api/service.py`; `src/artifacts/bundle.py`; `tests/test_api.py` | “With an explicitly configured, verified local bundle, FastAPI executes deterministic estimator inference and reports its own provenance and bounded result.” | That a trained bundle is committed, that the public site has a backend, or that this execution inherits Lane A/Lane B metrics |
| C14 | `/demo`, README, video | reference demo | `api/schemas.py`; `api/service.py`; `tests/test_api.py`; `web/components/demo/DeterministicJudgeDemo.tsx` | “Valid reference outcomes are human review or below review threshold; unavailable/error paths release no decision.” | “Safe,” “legitimate,” “approved,” “blocked,” “declined,” or “fraudulent” as system decisions |
| C15 | `/demo`, README, video | synthetic plumbing | `tests/test_api.py`; `web/__tests__/deterministic-demo.test.tsx`; `web/e2e/demo.spec.ts` | “Deterministic malformed-input tests demonstrate fail-closed HTTP 422 validation with no review outcome.” | Fraud-quality, adversarial robustness in production, or proof about real transactions |
| C16 | Dashboard/evidence, video | synthetic plumbing | `web/data/syntheticFixture.ts`; `web/components/SyntheticPlumbingSimulator.tsx`; `web/__tests__/synthetic-plumbing-simulator.test.tsx` | “Fabricated in-browser events demonstrate validation, contextual-signal, decision, and audit-shaped plumbing.” | Trained contextual model, real-time production signals, model accuracy, real fraud detection, or Razorpay data |
| C17 | `/demo`, README, video | reference demo | `api/audit.py`; `scripts/verify_api_audit_log.py`; `tests/test_api.py`; `docs/LIMITATIONS.md` | “Configured local audit is append-only and tamper-evident; same-process identical requests can replay the committed response and receipt without a second event.” | Immutable/WORM audit, tamper-proof storage, distributed audit, cross-restart exactly-once, or cross-replica idempotency |
| C18 | Evidence dashboard, engineering section | synthetic plumbing | `docs/benchmarks/P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md` §§3–7 | “The state-store checkout-exhaustion defect was repaired and three postfix proofs passed at four workers/concurrency 64; the subsequent frozen matrix failed closed at cell 10.” | Completed scale proof, production capacity, horizontal scalability, availability, or an RPS/SLO claim from the incomplete matrix |
| C19 | Evidence dashboard, optional engineering detail | synthetic plumbing | `docs/evidence/MT4_CONCURRENCY_EVIDENCE.md`; `docs/evidence/mt4/*.json` | “A named local-loopback, single-machine, single-worker historical/reference serving experiment may be quoted only with its exact environment and audit-growth caveat.” | Razorpay-scale performance, public-network latency, production throughput/SLO, multi-replica scale, or relation to fraud quality |
| C20 | README, dashboard, video, form | illustrative scenario | `docs/evidence/MT5_COST_EXPLORER_CONTRACT.md`; `docs/evidence/MT5_COST_EXPLORER_EVIDENCE.md`; `web/lib/laneACostModel.ts` | “Editable illustrative INR assumptions apply transparent arithmetic to published sealed aggregate counts.” | Razorpay/merchant economics, price, saving, ROI, avoided loss, forecast, recommendation, or optimal threshold/capacity |
| C21 | Evidence dashboard, video | historical | `reports/explainability/shap_summary_report.md`; `reports/explainability/shap_top_features.json`; `docs/LIMITATIONS.md` | “The historical SHAP artifact is a noncausal global ranking with output-unit and cohort limitations attached.” | Causal reason, per-request explanation, probability impact, protected-attribute fairness, or invented meanings for `V1`–`V28` |
| C22 | README, dashboard, form | administrative identity | `web/` source at `origin/main`; Vercel deployment record `dpl_9Jx19BdfNeE9PvGtZN3XgWpwRCpz` | “The static SecureSwipe frontend at `https://secure-swipe.vercel.app` serves source SHA `eb729a9...`.” | Public backend, uptime/SLA, live transaction service, or any model deployment inferred from the frontend |
| C23 | README, dashboard, form | administrative identity | Live HTTP checks; `web/components/Footer.tsx`; `web/public/secureswipe-methodology.html` | “The public `/`, `/evidence`, `/demo`, and methodology document were reachable with HTTP 200 at freeze time.” | Continuous availability, historical uptime, monitoring coverage, or future availability |
| C24 | README, video, form | administrative identity | GitHub checks for `eb729a9...`; `.github/workflows/*.yml` | “At freeze time, four of five reported checks succeeded and the Python check failed in its Test step.” | “All CI green,” “all tests pass,” or reusing test counts from older candidate SHAs as current |
| C25 | README, form, security section | synthetic plumbing | `docs/THREAT_MODEL.md`; `SECURITY.md`; audit/redaction tests; ignored-data policy | “The reference implementation has explicit input, logging, artifact, and fail-closed controls within the documented local scope.” | PCI DSS, SOC 2, ISO 27001, GDPR, RBI, bank-grade, penetration-tested, secure-for-production, or a real-data privacy program |
| C26 | README, dashboard, video, form | administrative identity | Repository search; `docs/LIMITATIONS.md`; `docs/evidence/EXECUTION_LEDGER.md` MT8 | “No Razorpay API, SDK, webhook, MCP, credential, or payment-flow integration is implemented.” | Razorpay integration, parity, endorsement, access to internal tools/data, or merchant deployment |
| C27 | README, dashboard, video | administrative identity | `docs/ARCHITECTURE.md`; diagram inventory below | “The architecture separates sealed offline evaluation, static presentation, and an opt-in local reference-serving path.” | Production reference architecture as implemented, cloud scale, or claim inheritance across the three paths |
| C28 | README, dashboard, video | reference demo | `api/service.py`; `web/data/metrics.ts`; `reports/operations/2026-08-25_genuine_model_api_benchmark.json` | “Core tabular scoring uses no LLM call; the recorded benchmark field reports zero LLM tokens for that measured path.” | Zero cost overall, zero compute, general AI independence for every development activity, or future usage guarantee |

## Diagram and Ideagram asset inventory

No filename contains “Ideagram,” and no Ideagram-specific metadata was found.
The two `Blank diagram` exports are the strongest candidates for the new overall
architecture visual. The SVG declares a `lucid` XML namespace, so its tool of
origin must not be described as Ideagram without separate provenance. The five
dark screenshots visibly correspond to five of the Mermaid blueprints.

The two `SecureSwipe diagrams` directories are distinct filesystem directories
but contain byte-identical copies of all seven files (matching SHA-256 per
corresponding filename). The outside-worktree copies are inventory only and are
not Git status entries for this repository.

| ID | Exact path | Format / dimensions | Git state | Likely purpose from visible content or filename |
| --- | --- | --- | --- | --- |
| D01 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/SecureSwipe diagrams/Blank diagram.png` | PNG, 2727×1827 | Untracked | Polished three-swimlane overview: offline Lane A science, static reviewer interface, and opt-in local reference demo |
| D02 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/SecureSwipe diagrams/Blank diagram.svg` | SVG, 2441.22×1751.06 | Untracked | Vector form of the polished three-path overview; SVG metadata uses `lucid` namespace |
| D03 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.33.51 PM.png` | PNG, 2810×560 | Untracked | Wide three-path system overview rendered in a dark diagram theme |
| D04 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.34.17 PM.png` | PNG, 1818×1390 | Untracked | `/demo` request, model-info, score, audit receipt, replay, and 422 validation sequence |
| D05 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.35.30 PM.png` | PNG, 2814×388 | Untracked | Lane A leakage-controlled development, quarantine, one-time final evaluation, and closure lifecycle |
| D06 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.35.50 PM.png` | PNG, 2812×572 | Untracked | Claim-to-evidence firewall separating illustrative, synthetic, historical, sealed, reference, and future categories |
| D07 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.36.17 PM.png` | PNG, 1354×1564 | Untracked | PostgreSQL V2 idempotency reservation, transactional audit, replay/conflict/fail-closed branches, and verifier |
| D08 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe diagrams/Blank diagram.png` | PNG, 2727×1827 | Outside worktree | Byte-identical duplicate of D01 |
| D09 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe diagrams/Blank diagram.svg` | SVG, 2441.22×1751.06 | Outside worktree | Byte-identical duplicate of D02 |
| D10 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.33.51 PM.png` | PNG, 2810×560 | Outside worktree | Byte-identical duplicate of D03 |
| D11 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.34.17 PM.png` | PNG, 1818×1390 | Outside worktree | Byte-identical duplicate of D04 |
| D12 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.35.30 PM.png` | PNG, 2814×388 | Outside worktree | Byte-identical duplicate of D05 |
| D13 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.35.50 PM.png` | PNG, 2812×572 | Outside worktree | Byte-identical duplicate of D06 |
| D14 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe diagrams/Screenshot 2026-08-31 at 8.36.17 PM.png` | PNG, 1354×1564 | Outside worktree | Byte-identical duplicate of D07 |
| D15 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/docs/DIAGRAM_BLUEPRINT_DRAFTS.md` | UTF-8 Markdown, 239 lines | Untracked | Seven source Mermaid specifications and required adjacent disclosures for the candidate diagrams |
| D16 | `/Users/mayanksuryavanshi/Downloads/DIAGRAM_BLUEPRINT_DRAFTS.md` | UTF-8 Markdown, 239 lines | Outside worktree | Byte-identical duplicate of D15 |
| D17 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/docs/ARCHITECTURE.md` | UTF-8 Markdown | Tracked at working HEAD; differs from `origin/main` through branch divergence | Canonical implemented-system architecture and boundary narrative for the working branch |
| D18 | `/Users/mayanksuryavanshi/Downloads/SecureSwipe-main/docs/ux/P0_1_INFORMATION_ARCHITECTURE.md` | UTF-8 Markdown, 236 lines | Tracked | Dashboard information architecture and claim-placement rules |
| D19 | `/Users/mayanksuryavanshi/Downloads/P0_1_INFORMATION_ARCHITECTURE.md` | UTF-8 Markdown, 236 lines | Outside worktree | Byte-identical duplicate of D18 |

Other immediate-directory files whose names contain “architecture” belong to
unrelated projects (earnings-call analysis or speaker segmentation) and are not
SecureSwipe assets. Scientific plots under `reports/figures/`, public dashboard
figures under `web/public/images/`, and ignored visual-review screenshots are
evidence/UI assets rather than architecture/Ideagram assets and are therefore
outside this inventory.

## Explicit do not claim list

- Do not call any model score a fraud probability. Lane A's recorded Platt
  calibration is scoped to the sealed benchmark output; the local historical
  reference bundle reports raw-score semantics.
- Do not claim the exact Lane A model is loadable, served, reconstructed, or
  demonstrated. Its serving chain is unavailable or cryptographically unproven.
- Do not attribute Lane A or Lane B metrics to `/demo`, the public frontend, or
  a retained reference bundle.
- Do not compare Lane A and Lane B metrics as if they were competing runs.
- Do not make Razorpay, Indian-payment, live-merchant, real-customer, future,
  or production fraud-performance claims.
- Do not claim autonomous allow, approval, block, decline, capture, settlement,
  refund, or adverse action.
- Do not call below-threshold cases safe, legitimate, non-fraudulent, approved,
  or authorized.
- Do not claim real Razorpay or merchant economics, savings, ROI, avoided loss,
  cost reduction, recommended capacity, optimal threshold, staffing default, or
  production policy from the INR explorer.
- Do not claim production scale, horizontal scaling, a capacity guarantee,
  public-network latency, availability, uptime, or an SLO. The P1-S4 matrix is
  incomplete and failed closed.
- Do not call the audit immutable, WORM, tamper-proof, distributed, or
  regulatory-grade; do not claim cross-restart/cross-replica exactly-once.
- Do not claim a public scoring backend or live merchant API. The verified
  public deployment is the frontend only.
- Do not describe the public recorded-reference path as live inference or a
  newly measured run.
- Do not claim all CI is green or reuse test counts from an older SHA; the
  current `origin/main` Python job is failing.
- Do not claim a verified pitch video; no URL exists in the inspected sources.
- Do not claim a Razorpay API/SDK/webhook/MCP integration or endorsement.
- Do not claim PCI DSS, SOC 2, ISO 27001, GDPR, RBI, bank-grade security,
  penetration testing, or a real-data privacy program.
- Do not claim protected-group fairness, causal SHAP explanations, or semantic
  interpretations of anonymized PCA fields `V1`–`V28`.
- Do not call the Lane A final role human-blind, externally blind, repeatedly
  evaluated, or eligible for reopening/tuning.
- Do not call any untracked or outside-worktree diagram a committed/public
  architecture asset, and do not call the Lucid-namespaced SVG an Ideagram
  export without separate provenance.

## Confirmed unresolved boundaries

1. The exact Lane A serving bundle remains unavailable or cryptographically
   unproven. This is a required disclosure, not a task to solve by reconstruction.
2. `/demo` remains a separate local reference-model demonstration. On the
   current public frontend, its fully traversable default is a recorded
   transcript, not live inference.
3. Public deployment source is now verified for the frontend at `eb729a9...`,
   but canonical documentation has not yet been updated to record that fact.
4. Scalability claims remain withheld. P1-S4 closed without a scale claim after
   the frozen matrix failed at cell 10.
5. No verified public backend, real Razorpay integration, or live-merchant
   evidence exists.

## Blockers for Block 2 onward

1. Perform Block 2 from a new clean worktree based on `origin/main` at
   `eb729a9...`; do not use or mutate the divergent dirty primary worktree.
2. Replace stale repository/deployment identities in `README.md`,
   `docs/DEPLOYMENT.md`, `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md`, and
   `docs/evidence/SUBMISSION_PACKAGE.md` with the verified deployment record.
   Preserve `MT9_RELEASE_FREEZE.md` as a dated historical record.
3. Rewrite the pitch/form package so sealed Lane A is the sole headline result;
   retain Lane B only as labelled historical evidence.
4. Diagnose and fix or explicitly disposition the Python CI failure on exact
   `origin/main` before any “all checks pass” statement.
5. Select one canonical architecture asset pair from the duplicate untracked
   sets, validate its wording against this ledger, and add it in a later
   authorized block. Do not publish the dirty README's SVG link until the chosen
   asset is committed with it.
6. Obtain and verify the real pitch-video URL before adding a video link or
   making a video-availability claim.
7. After Block 2 edits, run link, claim-string, clean-checkout test/build, and
   deployment-source checks against one exact candidate SHA before submission.

## Block 1 Verdict

**BLOCKED**

The evidence boundaries themselves are clear and sufficient for a truthful
submission, and the production frontend is now source-linked to current
`origin/main`. Submission work is nevertheless blocked because the canonical
README/deployment/submission documents contradict that verified deployment,
the existing pitch package promotes the wrong evidence lane and stale test
counts, current `origin/main` has a failing Python CI check, the architecture
assets are untracked and duplicated, and no verified pitch-video URL exists.

The exact next action for Block 2 is: create a clean worktree from
`eb729a9cc11646e84737703b911c9d333d955be9`, reconcile the four stale public
truth documents and the Lane A-first pitch/form language against this ledger,
and diagnose the Python CI failure—without changing models, thresholds,
evaluation artifacts, or the dirty primary worktree.
