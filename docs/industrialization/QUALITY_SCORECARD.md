# Industrial quality scorecard

Scores require command or artifact evidence. The baseline is intentionally
strict; a passing legacy test suite does not earn credit for unimplemented paths.

| Category | Available | Baseline | Evidence |
|---|---:|---:|---|
| ML correctness and scientific validity | 20 | 8 | Train-only scaling, strict finite/schema/duplicate validation, split isolation, historical-test quarantine, and internally consistent confusion metrics exist; OOT evaluation, uncertainty, calibration, cost analysis, and robust selection remain. |
| Reproducibility and data lineage | 15 | 5 | Seeds, frontend lock, deterministic fingerprints, runtime provenance, payload hashes, and a versioned complete bundle exist; Python locks and full run manifests remain. |
| Architecture and maintainability | 15 | 6 | Offline/static paths and the artifact boundary are separated; serving remains a placeholder and configuration/duplicate modules conflict. |
| Testing and quality gates | 15 | 8 | 166 Python tests plus frontend lint/type/build pass; artifact corruption is tested before deserialization, but API/container/scientific/frontend behavior and export/audit gates remain incomplete. |
| API/container reliability | 10 | 0 | API and Dockerfile are placeholders. |
| Security and privacy | 10 | 6 | No tracked data/secrets found, Kaggle credentials are ignored, frontend headers are useful, and local artifacts require trusted roots and pre-load integrity checks; automation/threat controls remain. |
| Observability and operations | 10 | 0 | No service metrics, structured logs, drift monitor, measured SLOs, or runbooks. |
| Documentation and developer experience | 5 | 3 | Persistent controls and corrected historical limitations now exist; cards/runbooks/policies remain. |
| **Total** | **100** | **36** | **First P0 batch verified locally; not yet an operational system.** |

## Evidence ledger

- Python: `145 passed` in 59.18 seconds on clean Python 3.12.10 arm64 environment.
- Frontend: data check, lint, typecheck, current test script, and production build all passed on Node 22.11.0.
- npm audit: zero known vulnerabilities in full and production-only scans.
- Docker: client present; daemon unavailable, so no image evidence.
- Data/model: absent by design; original AP/ROC and artifact behavior not reproducible.
- Historical confusion-matrix derived metrics: independently recomputed and matched.
- P0 batch: 166 Python tests passed; corrupt, incomplete, schema-mismatched,
  missing-checksum, and untrusted-path artifacts fail before deserialization.

The score will be updated only after each batch's acceptance commands pass.
