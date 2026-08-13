# Industrial quality scorecard

Scores require command or artifact evidence. The baseline is intentionally
strict; a passing legacy test suite does not earn credit for unimplemented paths.

| Category | Available | Initial | Current | Evidence |
|---|---:|---:|---:|---|
| ML correctness and scientific validity | 20 | 5 | 14 | Strict contracts/isolation, historical quarantine, forward folds, Wilson/paired bootstrap uncertainty, simplicity rule, calibration diagnostics, constrained metrics, and explicit cost engine are tested; original OOT/model comparison/calibration and SHAP-unit evidence remain blocked/open. |
| Reproducibility and data lineage | 15 | 2 | 12 | Hash-locked environments, fingerprints, bundle provenance, clean wheel, deterministic development manifests, full dashboard/figure digest, and side-effect-free export verification exist; authoritative config and legacy training manifests remain. |
| Architecture and maintainability | 15 | 4 | 12 | Offline/static and verified serving paths, mounted bundle image, and executable current audit are separated with explicit status semantics; run configuration and duplicate legacy modules remain. |
| Testing and quality gates | 15 | 6 | 14 | 267 Python tests, lint/types, scientific/API/container/tamper/determinism tests, executable audit, package proof, and frontend gates pass; daemon and real frontend behavior remain incomplete. |
| API/container reliability | 10 | 0 | 6 | Versioned API behavior, readiness, concurrency serialization, limits, and OpenAPI pass synthetic tests; container remains unverified and requires Docker Desktop. |
| Security and privacy | 10 | 3 | 8 | Trusted-root pre-load verification, strict validation, limits, CORS allowlists, redacted logs, ignored credentials, and a clean runtime vulnerability audit pass; automated scans/threat model remain. |
| Observability and operations | 10 | 0 | 3 | Bounded request/latency/score metrics and request-ID JSON logs are tested; drift monitoring, measured load/SLOs, alerts, and runbooks remain. |
| Documentation and developer experience | 5 | 3 | 5 | Persistent controls, API/container/scientific protocols, data/model cards, and limitations are explicit; broader contributor/security/incident policy remains but the category's core evidence is complete. |
| **Total** | **100** | **23** | **74** | **Export/current-audit integrity is verified; supply-chain, monitoring, frontend behavior, and external evidence remain.** |

## Evidence ledger

- Python: `145 passed` in 59.18 seconds on clean Python 3.12.10 arm64 environment.
- Frontend: data check, lint, typecheck, current test script, and production build all passed on Node 22.11.0.
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

The score will be updated only after each batch's acceptance commands pass.
