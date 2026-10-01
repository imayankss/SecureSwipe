# SecureSwipe diagram blueprint — draft Mermaid specifications

These are implementation drafts from the local working-tree architecture audit.
They are diagrams of verified boundaries, not claims of production deployment,
Razorpay integration, autonomous payment action, or benchmark-proven scale.

## 1. SecureSwipe: three paths, explicit evidence boundaries

```mermaid
flowchart LR
  R[Reviewer]

  subgraph OFF["Offline science — private/local boundary"]
    S[Authorized research source] --> C[Manifested curation]
    C --> D[Chronological development roles]
    D --> L["Sealed Lane A evaluation<br/>aggregates + digests only"]
  end

  subgraph STATIC["Static reviewer interface"]
    L --> X[Deterministic exporter]
    X --> J[Sanitized dashboard JSON]
    J --> H["Next.js /"]
    J --> E["Next.js /evidence"]
  end

  subgraph DEMO["Opt-in local reference demonstration"]
    F[Fixed sanitized fixture] --> W["Next.js /demo"]
    W --> A[FastAPI V1]
    B["Verified reference bundle<br/>not Lane A"] --> A
    A -. "when configured" .-> U[Local tamper-evident audit]
    A --> O["Bounded outcome"]
  end

  R --> H
  R --> E
  R --> W
  O --> P["Human reviewer decides<br/>payment action outside system"]
```

Required adjacent disclosure: the local demo does not serve the sealed Lane A
model; `/` and `/evidence` do not require a backend.

## 2. Deterministic local request and replay sequence

```mermaid
sequenceDiagram
  actor Reviewer
  participant UI as Next.js /demo
  participant API as FastAPI V1
  participant Idem as In-process idempotency
  participant Model as Verified reference bundle
  participant Audit as Optional local audit

  Reviewer->>UI: Start guided demo
  UI->>API: GET /v1/model-info
  API-->>UI: Bundle/version/provenance

  UI->>API: POST /v1/predict<br/>fixed sanitized body + fixed request ID
  API->>API: Validate schema and readiness
  API->>Idem: Reserve ID + canonical-input digest
  Idem-->>API: First owner
  API->>Model: Score once
  Model-->>API: Score metadata
  API->>API: Apply recorded threshold
  opt audit configured and healthy
    API->>Audit: Append chained event
    Audit-->>API: Original event hash
  end
  API-->>UI: Bounded decision + optional receipt
  UI-->>Reviewer: Human review / below threshold

  UI->>API: Replay identical ID and body
  API->>Idem: Lookup completed entry
  Idem-->>API: Cached response + original receipt
  API-->>UI: Same result<br/>X-Idempotent-Replay: true

  UI->>API: Malformed fixture
  API-->>UI: 422 validation_error<br/>no decision
```

Required adjacent disclosure: replay is same-process behavior for V1; audit
confirmation is unavailable when the API did not return a readable receipt.

## 3. Bounded decision and fail-closed state machine

```mermaid
stateDiagram-v2
  [*] --> Pending
  Pending --> Validate: request received
  Validate --> Unavailable: malformed / unready / integrity failure
  Validate --> Score: schema + bundle verified
  Score --> Unavailable: overload / timeout / invalid output
  Score --> Policy: finite result
  Policy --> HumanReview: at or above threshold
  Policy --> BelowThreshold: below threshold
  HumanReview --> HumanDecision: reviewer investigates
  BelowThreshold --> [*]: no review raised
  Unavailable --> [*]: no decision released

  note right of HumanDecision
    Payment authorization,
    decline, capture, and settlement
    remain outside SecureSwipe.
  end note
```

Required adjacent disclosure: “below review threshold” does not mean approved,
safe, legitimate, or non-fraudulent.

## 4. Lane A leakage-controlled evaluation lifecycle

```mermaid
flowchart LR
  A[Approved IEEE-CIS source] --> B[Manifested curation]
  B --> P[Chronological role assignment]

  subgraph DEV["Development boundary"]
    T[training] --> M["Fixed model families<br/>seed 42"]
    V[validation_threshold] --> S["Select variant E / XGBoost"]
    CF[calibration_fit] --> PC[Fit Platt calibrator]
    CE[calibration_eval] --> CD[Calibration decision]
    M --> S
    S --> F[Freeze pipeline + 24-input schema]
    PC --> F
    CD --> F
    F --> CP[Freeze capacity policy]
  end

  P --> T
  P --> V
  P --> CF
  P --> CE
  P --> Q["final_test quarantine"]

  CP --> AUTH[Digest-bound authorization]
  Q --> RUN[One-time guarded runner]
  AUTH --> RUN
  RUN --> SS[Compute and seal scores]
  SS --> LABELS[Open final labels]
  LABELS --> RESULT["Sealed aggregate metrics,<br/>intervals, counts, digests"]
  RESULT --> CLOSED["Closed: no tuning or rerun"]
```

Required adjacent disclosure: final_test was programmatically held out, not
human-blind or externally blind. The final output is offline evaluation evidence,
not API-serving evidence.

## 5. Claim-to-evidence firewall

```mermaid
flowchart TB
  A["SEALED<br/>Lane A evaluation"] --> AC["Headline offline metrics<br/>and capacity counts"]
  B["HISTORICAL<br/>Lane B record"] --> BC["Already-observed audit context"]
  R["REFERENCE<br/>Local bundle inference"] --> RC["Bundle/runtime/API behavior only"]
  S["SYNTHETIC<br/>Fixtures and plumbing"] --> SC["Validation, packaging,<br/>failure and workflow mechanics"]
  I["ILLUSTRATIVE<br/>Capacity/cost scenarios"] --> IC["Transparent arithmetic<br/>under explicit assumptions"]
  F["FUTURE<br/>Deferred capability"] --> FC["No implemented claim"]

  A -.-x R
  B -.-x R
  S -.-x AC
  I -.-x AC
```

The crossed edges must be labelled “no claim inheritance” in an SVG or HTML
version because Mermaid renderer support for cross-edge styling varies.

## 6. PostgreSQL V2 idempotency and transactional audit

```mermaid
flowchart TD
  Q["POST /v2/predict"] --> H["HMAC(request ID)<br/>canonical request digest"]
  H --> R["Atomic reserve<br/>INSERT ... ON CONFLICT"]

  R -->|different digest| C["409 idempotency_conflict"]
  R -->|completed| RE["Exact score-free replay<br/>original audit receipt"]
  R -->|reserved/stale/failed| FC["503 fail closed"]
  R -->|new owner| S["Score once<br/>outside DB transaction"]

  S --> G[Completion admission]
  G --> TX["Single PostgreSQL transaction"]
  TX --> IL[Lock idempotency row]
  IL --> HL[Lock chain head]
  HL --> AE[Append canonical audit event]
  AE --> BR["Store bounded response + hash + receipt"]
  BR --> CH[Advance chain head]
  CH --> COMMIT[Commit completed state]

  COMMIT --> OUT["Decision + original receipt"]
  V["Explicit full-chain verifier<br/>startup or operator command"] -. verifies .-> AE
  V -. verifies .-> CH
  V -. verifies .-> BR
```

Required adjacent disclosure: this is an opt-in, local PostgreSQL correctness
profile. It stores score-free bounded responses; the P1-S4 matrix did not
authorize a scalability, capacity, or production claim.

## 7. Review capacity: the two-sided operational trade-off

```mermaid
flowchart LR
  S["Sealed Lane A ranked aggregates"] --> B["Illustrative daily review budget"]
  B --> TOP["Highest-ranked selected population"]
  B --> REST["Remainder below review threshold"]
  TOP --> HR["Human-review queue"]
  HR --> OUT["TP + FP aggregate outcomes"]
  REST --> REM["FN + TN aggregate outcomes"]
  OUT --> N["Payment action outside system"]
```

Use this accompanying accessible table or SVG chart; do not imply a recommended
capacity or observed merchant economics.

| Illustrative reviews/day | Recall | Legitimate transactions sent to review |
| ---: | ---: | ---: |
| 100 | 27.18% | 2,239 |
| 250 | 45.70% | 6,285 |
| 500 | 64.39% | 13,404 |
| 1,000 | 80.18% | 28,306 |
| 2,000 | 93.84% | 58,663 |

Required adjacent disclosure: these are sealed IEEE-CIS aggregate results and
illustrative capacity tiers. They are not staffing defaults, Razorpay economics,
or a production operating recommendation.

## Source references

- `docs/ARCHITECTURE.md`
- `docs/EVIDENCE_GUIDE.md`
- `docs/MODEL_CARD.md`
- `docs/API.md`
- `docs/LIMITATIONS.md`
- `docs/evidence/LANE_A_FINAL_EVALUATION.md`
- `docs/evidence/LANE_A_FINAL_EVALUATION_PROTOCOL.md`
- `docs/evidence/CLAIM_TO_EVIDENCE_MATRIX.md`
- `docs/benchmarks/P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md`
- `api/main.py`, `api/audit.py`, `api/postgres_idempotency.py`, and `api/postgres_audit.py`
- `src/lane_a/capacity.py` and `scripts/lane_a_run_final_evaluation.py`
