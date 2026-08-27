# MT9 — local submission release freeze

**This candidate has not been pushed, deployed, tagged, or released.** It exists
only in this local repository. Publication requires separate owner approval.

## 1 — Candidate identity

| Item | Value |
| --- | --- |
| Candidate commit | `a8638abb849f02186a0200329ff3323831dcd349` |
| Parent (MT7) | `8974f018e434825453bfc859766da0a74812c35a` |
| Branch | `codex/recovered-demo-bundle` (branch-local, not on `main`) |
| **`web/` tree digest** | `7f4d60e90c864f2650f7640cab319a3806db8d53` |

## 2 — Evidence hash chain

| Document | SHA-256 |
| --- | --- |
| README.md | `81b0ea65c9b0211ad60aa230387b59763ec0486bc21c60dc3a1bc70e26100ade` |
| docs/ARCHITECTURE.md | `cda34ac616deb5b155cf4552eb3a976ccea7da4da9d6908cb6e5859ba7bfc6aa` |
| docs/LIMITATIONS.md | `a79c03abdd559542601dcd7ad59fc1d181b64f1cc108f3c1db843e0d6ee5084b` |
| CLAIM_TO_EVIDENCE_MATRIX.md | `482e2fd7e57b08a3b4799098c707551d96e1988fdb7c9b2d469a228e69129f83` |
| EXECUTION_LEDGER.md | `5125f9e392c825db5e5eae3adce89fc2ba37e5329a5edac503a721eb89a0b5d2` |
| MT9_CLAIM_PLAN.md | `bf9dd5aa6051345f066a64b7340880c22cbc45b112cc38780b1f585ef2feba14` |

### Frozen scientific artifacts — byte-identical since MT9 Phase 0

| Document | SHA-256 |
| --- | --- |
| LANE_A_FINAL_EVALUATION.md | `0f85666dac15ff85cd6a8bcd70c79b1817fb497ec667e40638ac7fc5136c5034` |
| MT4_CONCURRENCY_EVIDENCE.md | `1e84a50cdd24e3fcac40a5daa50dd2938b7c8d61d678f760ef8a36ffbcfadd41` |
| MT5_COST_EXPLORER_EVIDENCE.md | `5e9a263f7dc2e7171c2c59fcfc76ced4c4e0dda6e41956e22d8d1f3f417b08ae` |
| MT6_STATE_AND_CRASH_DECISION.md | `a1701653a3a40a03b3dff7dc212f1d6d1fe5762c67df6752cd104e7f5aea60f2` |
| MT7_ORDER_INTEGRITY_DECISION.md | `9d80466d14cfc1d65ea012e3d50aa2bf3f0129ff072fc73bbb5bba9b8694c167` |
| web/data/laneACapacity.ts | `5a0906f6fb30eb01c17b33512d21e4a29935b33a53d27adaa463be0afc2076f7` |
| api/main.py | `ae2717b401ea6eee7b29905681fb74993fc6ad95edff1bf726be1795a9af723d` |

## 3 — Verification results at the candidate commit

| Gate | Result |
| --- | --- |
| Accepted canonical Python suite | **1,269 passed, 0 failed** |
| Ruff (`src scripts tests`) | clean |
| Ruff (`notebooks/`) | 12 pre-existing legacy findings, reported separately, untouched |
| mypy (30 Lane A / operations / order-integrity files) | clean |
| Frontend gate (data-check, ESLint, TypeScript, Vitest) | **85 passed** |
| Static production build | succeeded |
| Playwright E2E | **10 passed** |
| Accessibility (axe, panel-scoped) | zero violations |
| 375 px horizontal overflow | none, panel or page |
| `git diff --check` | clean |
| Relative-link integrity | 18 checked, 0 broken |
| Secret / private-path / private-artifact / large-file scans | clean |

Node pinned `22.13.1`; Python `3.12.10`, arm64 Darwin.

## 4 — Deployment relationship

The documented public URL `https://secure-swipe.vercel.app/` returned **HTTP
200** on a read-only probe during MT9. It **does not represent this candidate**:
the served page contains none of the sealed Lane A figures (`0.208660`,
`80.18 %`, `88,581` rows), no Lane A capacity workbench, and no cost explorer.
It is an older Lane B-only build, and it exposes no commit SHA or build metadata,
so no linkage can be established in either direction.

**Deployment-to-SHA linkage remains `BLOCKED`.** Nothing was pushed, deployed,
aliased, tagged, or released by this task.

## 5 — What a reviewer sees first

The primary result is the **sealed Lane A final evaluation**: AP `0.208660`
(95 % CI `0.195700`–`0.222711`), ROC-AUC `0.814975`, one programmatically
held-out IEEE-CIS evaluation run exactly once. At 1,000 reviews/day it reaches
`80.18 %` recall at `8.03 %` alert precision — `2,472` caught, `611`
missed, `28,306` legitimate transactions sent to human review.

A false positive is a legitimate transaction **sent to human review, never
automatically declined**. No capacity tier is optimal, recommended, or a default.

The older Lane B historical AP `0.8288` is retained only inside its own
historical-evaluation section and is never promoted above, or compared with, the
Lane A result.

## 6 — Outstanding manual inputs

- A **real pitch-video URL**, if one is to appear. No placeholder was added.
- **Owner approval to push** this candidate and deploy that exact `web/` tree.
- **Final submission-form confirmation.**

## 7 — Non-claims

No CI result, deployed SHA, live API, internship outcome, merchant result,
saving, ROI, production SLO, Razorpay-scale throughput, or live fraud-detection
claim is made by this freeze. `final_test` was not accessed; no model,
threshold, capacity policy, calibration, or frozen evidence changed.
