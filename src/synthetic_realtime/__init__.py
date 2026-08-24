"""Isolated synthetic real-time plumbing layer.

Everything in this package is artificial: opaque synthetic tokens, a
transparent bounded heuristic score, and reason codes used only to
demonstrate real-time feature/state/decision plumbing. Nothing here is a
fraud probability, a production risk score, or a claim about the locked
historical evaluation. This package must never import the historical
XGBoost model, SHAP, thresholds, metrics, or Bundle v3 code.
"""

from __future__ import annotations
