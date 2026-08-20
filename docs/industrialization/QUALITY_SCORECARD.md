# Industrial quality scorecard

Scores require command or artifact evidence. The baseline is intentionally
strict; a passing legacy test suite does not earn credit for unimplemented paths.

| Category | Available | Initial | Current | Evidence |
|---|---:|---:|---:|---|
| ML correctness and scientific validity | 20 | 5 | 17 | Historical-corpus quarantine, operator-attested exact-file approval, deterministic curation, four chronological content-hash-isolated roles, matched random diagnostic, paired uncertainty/simplicity selection, calibration, reusable forward backtest, constrained/cost metrics, and raw-margin SHAP protocols are synthetic-tested; real new-data and historical SHAP execution remain external blockers. |
| Reproducibility and data lineage | 15 | 2 | 15 | Hash-locked environments/toolchain, fingerprints, bundle provenance, clean wheel, atomic timestamp-free manifests for development and every legacy stage, typed configuration, historical lock, and read-only export verification are tested. |
| Architecture and maintainability | 15 | 4 | 15 | Offline/static, blocked-development, reference-stage, and verified serving paths have explicit boundaries; direct partial legacy CLIs fail closed; mounted bundles, current audit, workflow separation, typed configuration, and governance are tested. |
| Testing and quality gates | 15 | 6 | 15 | 343 Python tests, lint/types, scientific/API/container/tamper/determinism/supply-chain/wheel-inventory tests, clean package proof, seven focused component tests, and three production Chromium keyboard/mobile/WCAG/static-boundary/live-fallback tests pass; two unchanged final cycles remain. |
| API/container reliability | 10 | 0 | 10 | Versioned API, readiness, limits, OpenAPI, exact parity, threadpool offload, runtime log evidence, health responsiveness, and the final ARM64 read-only/non-root/pip-free container pass. |
| Security and privacy | 10 | 3 | 10 | Trusted-root loading, validation/limits/CORS/redacted logs, clean dependency audits, least-privilege CI, final-image Trivy review, expiring per-CVE mitigations, and an SPDX SBOM pass locally; remote secret/code workflows remain external evidence. |
| Observability and operations | 10 | 0 | 9 | Bounded metrics/logs, deterministic offline monitoring, incident/rollback guides, repeated host measurements, and a zero-error 500-request final-container probe pass; provider behavior remains unmeasured. |
| Documentation and developer experience | 5 | 3 | 5 | Persistent controls, architecture/data flow, API/container/scientific/monitoring protocols, data/model cards, threat/limitations/deployment/reproducibility guides, interview defense, demo, and local incident guidance are explicit and link-checked. |
| **Total** | **100** | **23** | **96** | **Local scientific protocols, reproducibility, architecture, API, container, monitoring, security scan, and behavioral/static frontend gates are evidence-backed; real new-data and remote CI remain external blockers.** |

## Evidence ledger

- Python: `145 passed` in 59.18 seconds on clean Python 3.12.10 arm64 environment.
- Frontend: data check, lint, typecheck, current test script, production build,
  and npm audit passed on isolated official Node 22.13.1/npm 10.9.2.
- npm audit: zero known vulnerabilities in full and production-only scans.
- Docker: final ARM64 image `sha256:a16cb318...` passed restricted startup,
  readiness, exact golden inference, metrics/OpenAPI, bounded load, Trivy review,
  and SPDX SBOM generation.
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
- Frontend behavior batch: seven Vitest/Testing Library component tests and
  three production Chromium tests pass on Node 22.13.1. The browser verifies
  skip-link focus, keyboard score changes, responsive section navigation, named
  status/table/progress/chart semantics, a clean WCAG A/AA Axe scan, the
  unconfigured synthetic-demo fallback, and zero requests to `/v1/predict`;
  full npm audit reports zero vulnerabilities.
- Maintainability/supply-chain/documentation batch: 21 unreachable source/script
  placeholders, four zero-test files, one stale report, and the unused Streamlit
  closure were removed after reference search; all 320 tests still pass. The
  quality and isolated resolver locks install cleanly, audit with no known
  vulnerabilities, and the quality lock regenerates identically twice at
  `46507a91ea208ba3ad26b6f4f6bbffbdf3e6a0f9772fbe36c5746eb075170a7b`.
  The expanded executable audit has 14 passing commands plus an explicitly
  unavailable bundle, and 23 documentation files have valid local links.
- Frontend performance evidence: the clean production page measured 270,718
  encoded script bytes across six scripts and 329,437 total bytes across ten
  requests. Chromium now enforces 350,000/8 script and 450,000/12 total budgets;
  timings are recorded for context but not asserted as a local-run SLO.
- Adversarial artifact review rejected the first nominally green cycle because a
  direct wheel build contained 16 deleted modules from ignored `build/lib`.
  Release gates now build wheel-from-sdist without isolation/network resolution,
  then compare all packaged `api/` and `src/` Python modules with current source.
  Three failure-mode tests and the corrected 49-source-module/54-member wheel
  inventory pass.
- Runtime hardening proof: the API lock and corrected wheel were installed into
  a clean environment, pip was removed, and the API/bundle imports still passed.
  The Dockerfile and static tests enforce removal before switching to UID 10001;
  final image execution/scan remains blocked by the stopped daemon.
- Bundle/public-claim adversarial batch: 328 Python tests, Ruff, critical mypy,
  dependency-free export verification, five component tests, and the production
  frontend build pass. Bundle format 2 rejects reversed class mappings and
  preprocessor/model skew, records/checks SciPy and XGBoost before loading, and
  executes a checksummed canonical probe before readiness. Workflow policy now
  scans non-verified history candidates and specifies exact golden response,
  UID, and pip-free container checks; remote/container execution remains blocked.
- Scientific-lineage batch: 339 tests collect and the focused 33-test
  curation/development/bundle/config suite passes with Ruff and mypy. Two
  separate synthetic runs are byte-identical, including fitted bundle bytes and
  manifests. Conflicting duplicates, known historical signature/path, renamed
  row fingerprints, source-label mismatch, chronology violations, reference-
  only curation, and partial/overwrite paths fail closed. Untouched evaluation,
  reloaded bundle, and API service score hashes match exactly.
- Evidence-provenance/platform-lock batch: 342 tests pass in 17.40 seconds;
  Ruff, 29-file mypy, and 40 focused adversarial tests pass. Curation manifests,
  exact-file approvals, and score recomputation reject tampering. Darwin/Linux
  API and quality locks regenerate byte-identically twice and all four audit with
  no known vulnerabilities; Linux closures use CPU-only XGBoost with no NVIDIA
  packages.
- Final container batch: image `sha256:a16cb318...` runs Python 3.12.13 as UID
  10001 with a read-only root, no capabilities, no-new-privileges, and no pip.
  Exact golden inference passed. A 500-request container probe had zero errors,
  p50/p95/p99 28.33/38.08/147.06 ms, and concurrent health 20.01 ms. Trivy
  0.70.0 found 12 unique no-fix Debian advisories; each has a documented
  mitigation and 2026-09-20 expiry, leaving zero active reviewed findings. The
  SPDX 2.2 SBOM contains 117 packages and hashes to `03559fcf...`.

The score will be updated only after each batch's acceptance commands pass.
