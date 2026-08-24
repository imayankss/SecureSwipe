"""Feature families for the synthetic real-time plumbing layer.

Each module here computes transparent, deterministic, illustrative signals
and bounded window features from a ``SyntheticEventStore`` and the current
``SyntheticEvent``. Thresholds are synthetic/illustrative constants, not
tuned fraud thresholds, and nothing here is a fraud probability. This
package must never import the historical XGBoost model, SHAP, thresholds,
metrics, or Bundle v3 code.
"""

from __future__ import annotations
