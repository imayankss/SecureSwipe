# Industrial quality scorecard

Scores require command or artifact evidence. The baseline is intentionally
strict; a passing legacy test suite does not earn credit for unimplemented paths.

| Category | Available | Initial | Current | Evidence |
|---|---:|---:|---:|---|
| ML correctness and scientific validity | 20 | 5 | 15 | Strict contracts/isolation, historical quarantine, forward folds, uncertainty, simplicity rule, calibration, constrained/cost metrics, and raw-margin SHAP additivity/cohort evidence are tested; original OOT/model comparison/calibration and historical SHAP execution remain blocked. |
| Reproducibility and data lineage | 15 | 2 | 15 | Hash-locked environments/toolchain, fingerprints, bundle provenance, clean wheel, atomic timestamp-free manifests for development and every legacy stage, typed configuration, historical lock, and read-only export verification are tested. |
| Architecture and maintainability | 15 | 4 | 15 | Offline/static, blocked-development, reference-stage, and verified serving paths have explicit boundaries; direct partial legacy CLIs fail closed; mounted bundles, current audit, workflow separation, typed configuration, and governance are tested. |
| Testing and quality gates | 15 | 6 | 15 | 320 Python tests, lint/types, scientific/API/container/tamper/determinism/supply-chain tests, package proof, four component tests, and two production Chromium keyboard/mobile/WCAG/static-boundary tests pass; Docker execution remains explicitly blocked. |
| API/container reliability | 10 | 0 | 8 | Versioned API, readiness, limits, OpenAPI, exact parity, threadpool offload, runtime log evidence, health responsiveness, and 500-request loopback behavior pass; container remains unverified. |
| Security and privacy | 10 | 3 | 9 | Trusted-root pre-load verification, strict validation, limits, CORS allowlists, redacted logs, ignored credentials, clean runtime/npm audits, least-privilege immutable CI, governance, and threat model pass locally; remote secret/code and image scans remain unexecuted. |
| Observability and operations | 10 | 0 | 8 | Bounded metrics, runtime JSON/redaction evidence, deterministic schema/feature/score/delayed-label monitoring, shifted demo, repeated M2 load evidence, local objectives, and incident/rollback guides pass; container/provider operations remain unmeasured. |
| Documentation and developer experience | 5 | 3 | 5 | Persistent controls, API/container/scientific/monitoring protocols, data/model cards, security policy, threat model, and local incident guidance are explicit; broader architecture/reproducibility/interview material remains. |
| **Total** | **100** | **23** | **90** | **Local scientific protocols, reproducibility, architecture, API, monitoring, and behavioral/static frontend gates are evidence-backed; container, remote CI, and original-data execution remain.** |

## Evidence ledger

- Python: `145 passed` in 59.18 seconds on clean Python 3.12.10 arm64 environment.
- Frontend: data check, lint, typecheck, current test script, production build,
  and npm audit passed on isolated official Node 22.13.1/npm 10.9.2.
- npm audit: zero known vulnerabilities in full and production-only scans.
- Docker: client present; daemon unavailable, so no image evidence.
- Data/model: absent by design; original AP/ROC and artifact behavior not reproducible.
- Historical confusion-matrix derived metrics: independently recomputed and matched.
- P0 batch: 166 Python tests passed; corrupt, incomplete, schema-mismatched,
  missing-checksum, and untrusted-path artifacts fail before deserialization.
- API/reproducibility batch: 196 Python tests passed in 5.68 seconds;
  repository Ruff and focused mypy checks passed; a fresh hash-locked API venv
  installed the wheel and imported it outside the checkout; `pip-audit` found
  no known vulnerability in `requirements/api.lock`.
- API contracts: missing model returns non-ready/503 while liveness remains 200;
  corrupt configured bundle aborts startup; direct and service predictions match;
  validation, batch/body limits, concurrency, redacted logs, metrics, and OpenAPI are tested.
- Container-policy batch: deterministic synthetic smoke bundle plus 211-test
  full suite passed; image/source/context/non-root/health policies are tested.
  Docker daemon execution, image CVE scan, and SBOM remain explicitly blocked.
- Scientific batch: 251 Python tests passed in 6.82 seconds; forward-fold,
  calibration-partition, uncertainty, cost-accounting, finite-input, and
  deterministic run-manifest behavior are covered with synthetic evidence.
- Export/audit batch: read-only hash snapshot passed; tamper cases fail; nine
  project gates executed twice while the absent model remained explicitly
  `UNAVAILABLE` and the overall current audit remained `INCOMPLETE`.
- Supply-chain batch: 274 tests, Ruff, focused mypy, frontend production build,
  npm audit, and API pip-audit pass; the quality lock is byte-identical across
  two regeneration passes. Three workflow files parse as YAML and seven policy
  tests enforce immutable action refs, least privilege, no publication/deploy,
  multi-architecture scan/SBOM intent, and governance inventory. These workflow
  definitions are not counted as remote execution evidence.
- Monitoring/operations batch: 295 tests, Ruff, and 23-file mypy pass. Synthetic
  drift evidence is byte-deterministic and distinguishes two feature signals
  from absent score drift. An actual loopback Uvicorn run emitted 504 parseable,
  vector-free JSON records. Its tracked 500-request M2 result had zero errors,
  p50/p95/p99 25.98/29.99/38.72 ms and concurrent health 9.82 ms; three additional
  runs also had zero errors and exposed p99 jitter up to 78.79 ms. These are local
  synthetic measurements, not a real-model/container/deployment capacity claim.
- A newly published high-severity nanoid advisory caused the executable npm gate
  to fail during this cycle; the transitive package is now locked to fixed
  3.3.18. Fresh `npm ci`, audit (zero findings), test, and build pass on Node 22.13.1.
- Configuration/historical-integrity batch: 136 focused runner/config/scientific
  tests and 15 export/lock tests pass. Three evidence files verify against the
  tracked SHA-256 lock; the disabled historical runner exits 2; the web exporter
  verifies the lock before reading metrics. The one-time migration recorded
  `metrics_changed: false`, and threshold/report tests reject stale constants.
- SHAP-validity batch: 307 Python tests, repository Ruff, focused mypy, and the
  Node 22.13.1 frontend gates pass. A fitted synthetic binary-logistic XGBoost
  reconstructs native raw margin from base plus SHAP within `1e-5`; unsupported
  estimator output fails closed; cohort evidence is byte-deterministic. The
  historical ranking remains explicitly unverified because its model/rows are absent.
- Atomic evidence batch: 320 tests, Ruff, critical-path mypy, and isolated
  reference-wrapper mypy pass. An actual synthetic Day 2 stage produces
  byte-identical reports/manifests in separate targets. Injected stage and
  manifest failures leave no published directory; existing empty targets are
  preserved. The executable audit's 12 commands pass twice while the missing
  serving model remains truthfully `UNAVAILABLE`/`INCOMPLETE`.
- Frontend behavior batch: four Vitest/Testing Library component tests and two
  production Chromium tests pass on Node 22.13.1. The browser verifies skip-link
  focus, keyboard score changes, responsive section navigation, named status/
  table/progress/chart semantics, a clean WCAG A/AA Axe scan, and zero requests
  to `/v1/predict`; full npm audit reports zero vulnerabilities.

The score will be updated only after each batch's acceptance commands pass.
