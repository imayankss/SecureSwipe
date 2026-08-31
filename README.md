# SecureSwipe — AI Risk Manager

SecureSwipe is a defense-only fraud-risk detector and human-review decision aid.
It connects held-out model evidence to the operational question a reviewer must
answer: how much suspicious activity can a fixed review team inspect, and what
legitimate-customer workload comes with that choice?

It does **not** authorize, approve, block, capture, or decline payments.

## Demo and video

| Resource | Where to start |
| --- | --- |
| Product dashboard | [Run the static Next.js application locally](docs/REPRODUCIBILITY.md#static-dashboard) |
| Interactive walkthrough | [Run the local reference-model demonstration](docs/REPRODUCIBILITY.md#local-reference-model-demonstration), then open `/demo` |
| Evidence route | Open `/evidence` after starting the local dashboard |

A verified pitch-video link is not yet available; it will be added before
submission.

No public dashboard is presented here as the current candidate because its
source revision has not been independently verified. The integrity procedure is
documented in [Deployment](docs/DEPLOYMENT.md).

## Problem and intended user

Fraud is rare, so a ranking metric alone does not describe an operationally
useful detector. A threshold or review budget also changes:

- how many labelled fraud cases reach a reviewer;
- how many labelled fraud cases are missed;
- how many legitimate transactions consume review capacity; and
- how much uncertainty remains outside the available evidence.

SecureSwipe is intended for technical reviewers, risk analysts, and model
operators evaluating a human-review workflow in a controlled research or local
reference setting. It is not intended for real customer transactions or
automated adverse action.

## Headline Lane A result

`SEALED FINAL EVALUATION — LANE A / IEEE-CIS`

| Metric | Result | Committed source |
| --- | ---: | --- |
| Average precision | **0.208660** (95% CI `0.195700`–`0.222711`) | [Lane A §3](docs/evidence/LANE_A_FINAL_EVALUATION.md#3--aggregate-metrics) |
| ROC-AUC | **0.814975** (95% CI `0.806402`–`0.822899`) | [Lane A §3](docs/evidence/LANE_A_FINAL_EVALUATION.md#3--aggregate-metrics) |
| Recall at 1,000 reviews/day | **80.18%** | [Lane A §5](docs/evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results) |
| Alert precision at 1,000 reviews/day | **8.03%** | [Lane A §5](docs/evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results) |
| Evaluation population | 88,581 transactions · 3,083 fraud labels | [Lane A §2](docs/evidence/LANE_A_FINAL_EVALUATION.md#2--dataset-composition) |

This was one programmatically held-out IEEE-CIS evaluation, run exactly once
under a predeclared protocol. It is not human-blind or externally blind, not a
live-merchant result, and not a forecast.

Lane A is the sole headline evaluation. Older Lane B historical evidence remains
available for auditability but is not compared with Lane A.

## Product workflow

1. **Inspect the headline evidence.** The product route leads with the sealed
   Lane A result and its review-capacity implication.
2. **Choose an illustrative review budget.** The workbench exposes how recall,
   alert precision, missed fraud, and legitimate reviews move together.
3. **Change explicit cost assumptions.** The cost explorer performs transparent
   arithmetic over published aggregate counts; it does not choose a policy.
4. **Trace every claim.** The evidence route separates sealed evaluation,
   historical serving, synthetic checks, and illustrative scenarios.
5. **Exercise the local reference path.** `/demo` sends one fixed sanitized
   fixture to a configured local API and verifies bounded output, audit receipt,
   idempotent replay, and fail-closed validation.

The interactive `/demo` is a **local reference-model demonstration** separate
from the sealed Lane A evaluation. P0.4 found that the exact Lane A serving
artifacts are unavailable or unproven, so the route does not claim to serve the
headline model and never substitutes a fabricated result.

## Review-capacity trade-off

At the illustrative 1,000-reviews/day tier, Lane A selected 30,778 transactions
over the evaluation period. It sent 2,472 labelled fraud cases and 28,306
legitimate transactions to review, while 611 labelled fraud cases were not
selected. [Source: sealed Lane A capacity results.](docs/evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results)

A false positive here means a legitimate transaction sent to a human reviewer.
It does not mean an automatically rejected payment.

| Reviews/day | Recall | Alert precision | Legitimate reviews | Missed fraud | Source |
| ---: | ---: | ---: | ---: | ---: | --- |
| 100 | 27.18% | 27.23% | 2,239 | 2,245 | [Lane A §5](docs/evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results) |
| 500 | 64.39% | 12.90% | 13,404 | 1,098 | [Lane A §5](docs/evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results) |
| 1,000 | 80.18% | 8.03% | 28,306 | 611 | [Lane A §5](docs/evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results) |
| 2,000 | 93.84% | 4.70% | 58,663 | 190 | [Lane A §5](docs/evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results) |

Higher capacity improves recall while increasing legitimate-customer review
work. No tier is recommended, optimal, or a merchant default. Monetary outputs
are illustrative sensitivity calculations—not savings, ROI, or observed costs.
See the [cost-explorer evidence](docs/evidence/MT5_COST_EXPLORER_EVIDENCE.md).

## Architecture

```text
sealed Lane A aggregates ──► deterministic export ──► static Next.js UI
                                                           │
fixed synthetic fixture ──► local FastAPI ──► verified reference bundle
                                  │                    │
                                  ├─ fail-closed guards│
                                  └─ audit + replay ◄──┘
```

The paths are intentionally separate:

- **Offline Lane A science** owns the sealed headline evaluation.
- **Static presentation** receives aggregate evidence, never rows or model
  bytes.
- **Local reference serving** loads a checksum-verified bundle and emits only
  bounded review decisions; it is not the sealed Lane A model.
- **Optional prototypes** for local durability and synthetic order integrity sit
  outside the default prediction path.

The complete component, data-flow, concurrency, and trust-boundary explanation
lives only in [Architecture](docs/ARCHITECTURE.md).

## Run locally

Prerequisites are CPython 3.12.10 and Node.js 22.13.1. Use isolated environments
and the committed lockfiles; do not install project dependencies globally.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/quality.lock
cd web
nvm use 22.13.1
npm ci
cd ..
```

Start the static dashboard:

```bash
cd web
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

For the deterministic local reference-model demo, generate the synthetic bundle,
enable an audit sink, start the API, and build the frontend with its explicit
local API origin. Use the exact commands in
[Reproducibility](docs/REPRODUCIBILITY.md#local-reference-model-demonstration).

The API must remain live-but-unready when no verified bundle is configured.
Never provide it real cardholder or customer data.

## Evidence and reproducibility

Start with the [Evidence Guide](docs/EVIDENCE_GUIDE.md). It maps reviewer
questions to the appropriate evidence category and preserves the Lane A/Lane B
boundary.

| Need | Canonical document |
| --- | --- |
| Claim status and admissibility | [Claim-to-evidence matrix](docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md) |
| Chronological execution record | [Execution ledger](docs/evidence/EXECUTION_LEDGER.md) |
| Sealed headline evaluation | [Lane A final evaluation](docs/evidence/LANE_A_FINAL_EVALUATION.md) |
| Environment and deterministic checks | [Reproducibility](docs/REPRODUCIBILITY.md) |
| Local API contract | [API guide](docs/API.md) |
| Model intent and serving boundary | [Model card](docs/MODEL_CARD.md) |
| Deployment integrity | [Deployment](docs/DEPLOYMENT.md) |

Data-free integrity checks:

```bash
.venv/bin/python scripts/export_web_data.py --check
.venv/bin/python scripts/verify_historical_observation.py
```

These commands verify committed artifacts and cross-file invariants. They do not
rerun, tune, or reproduce the sealed Lane A evaluation. The exact Lane A model
chain is not present as a proven serving bundle.

The curation contract keeps `--source-kind historical_kaggle_reference`
separate from `--source-kind new_authorized_development`; new development uses
`scripts/run_development_training.py`. For a data-free repository audit, use
`python3 -m scripts.run_project_audit --allow-missing-model --check`. When a
verified bundle is available, run `python3 -m scripts.run_project_audit` without `--allow-missing-model`.

## Limitations

- Lane A is one offline evaluation on a public research dataset. It does not
  establish performance under domain shift, concept drift, or a live review
  operation.
- The held-out role was enforced programmatically, not by an independent party.
- The local reference bundle is separate from Lane A and must not inherit its
  metrics.
- Serving measurements are local loopback evidence, not public-network capacity
  or an SLO.
- Scores and attributions do not establish causal explanations, protected-group
  fairness, or real-world fraud probability.
- Cost inputs are editable illustrative assumptions and omit real staffing,
  queueing, delayed labels, and customer-remediation processes.
- Authentication, authorization, TLS termination, durable remote audit storage,
  multi-replica state, and a public backend are not established here.
- No Razorpay API, SDK, webhook, credential, or field integration is implemented.

The authoritative and complete boundary is
[Limitations and non-goals](docs/LIMITATIONS.md).

## Technology and author

| Layer | Components |
| --- | --- |
| Modeling | Python, pandas, NumPy, scikit-learn, XGBoost, SHAP |
| Serving | FastAPI, Uvicorn, Pydantic |
| Product UI | Next.js, React, TypeScript, Tailwind CSS, Recharts |
| Verification | pytest, Ruff, mypy, Vitest, Playwright, axe-core |
| Supply chain | Hash-locked Python dependencies, npm lockfile, GitHub Actions, CodeQL, TruffleHog, Trivy, SPDX SBOM |

Repository map: `api/` serving, `src/` model/evidence libraries, `scripts/`
deterministic commands, `reports/` aggregate artifacts, `docs/` canonical proof,
and `web/` the static reviewer interface.

SecureSwipe was created by **Mayank Suryavanshi**. Contributions must preserve
the evidence boundaries in [Contributing](CONTRIBUTING.md). Security reports
follow [SECURITY.md](SECURITY.md). The project is available under the
[MIT License](LICENSE).
