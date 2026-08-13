# Current Project Audit Checklist

Overall status: **INCOMPLETE**

`PASS` is reserved for an executed verification. `PRESENT` means only a
non-empty file inventory check. `UNAVAILABLE` is an explicit external/local
artifact blocker and must not be interpreted as passing.

| Status | Item | Evidence |
|---|---|---|
| PRESENT | README | `README.md` |
| PRESENT | Day 2 EDA report | `reports/day2_eda_summary.md` |
| PRESENT | Day 3 preprocessing report | `reports/day3_preprocessing_summary.md` |
| PRESENT | Day 4 baseline report | `reports/day4_baseline_model_summary.md` |
| PRESENT | Day 5 model comparison report | `reports/model_comparison/day5_model_comparison.md` |
| PRESENT | Day 6 threshold report | `reports/threshold_tuning/day6_threshold_tuning_report.md` |
| PRESENT | Day 7 SHAP report | `reports/explainability/shap_summary_report.md` |
| PRESENT | Final evaluation JSON | `reports/final/final_model_evaluation.json` |
| PRESENT | Final evaluation report | `reports/final/final_evaluation_report.md` |
| PRESENT | SHAP top features | `reports/explainability/shap_top_features.json` |
| PRESENT | API application | `api/main.py` |
| PRESENT | Container definition | `Dockerfile` |
| PASS | Python compile | `python -m compileall -q api src scripts tests` |
| PASS | Python lint | `python -m ruff check api src scripts tests` |
| PASS | Critical Python types | `python -m mypy --ignore-missing-imports api src/artifacts src/inference/risk_scoring.py src/evaluation/statistical_metrics.py src/evaluation/calibration.py src/evaluation/cost_analysis.py src/evaluation/temporal_validation.py src/utils/run_manifest.py scripts/run_development_analysis.py` |
| PASS | Python tests | `python -m pytest` |
| PASS | Web artifact determinism | `python scripts/export_web_data.py --check` |
| PASS | API dependency vulnerabilities | `python -m pip_audit -r requirements/api.lock --disable-pip --progress-spinner off` |
| PASS | Frontend test gate | `npm test` |
| PASS | Frontend production build | `npm run build` |
| PASS | Frontend dependency vulnerabilities | `npm audit --audit-level=high` |
| UNAVAILABLE | Verified serving model bundle | `SECURESWIPE_BUNDLE_MANIFEST is not configured` |
