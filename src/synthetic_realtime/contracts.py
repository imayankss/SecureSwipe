"""Strict, versioned contracts for the synthetic real-time plumbing layer.

These describe artificial, opaque-token events and their derived output used
only to demonstrate real-time feature/state/decision plumbing. Nothing here
is a fraud probability, a production risk score, or a claim about the locked
historical evaluation (see ``context.md``). This module must never import
the historical XGBoost model, SHAP, thresholds, metrics, or Bundle v3 code.

Terminology is deliberately restricted: ``decision`` and ``evidence_type``
are closed ``Literal`` sets, and free-text fields are screened for a small
set of forbidden terms, so this layer can never claim to approve, block, or
score fraud probability.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

# --- Versioning -------------------------------------------------------------

SYNTHETIC_SCHEMA_VERSION: Literal["1.0"] = "1.0"
EVIDENCE_TYPE_SYNTHETIC_PLUMBING_TEST: Literal["synthetic_plumbing_test"] = (
    "synthetic_plumbing_test"
)

# --- Bounds ------------------------------------------------------------------

MAX_TOKEN_BODY_LENGTH = 60
MAX_ID_LENGTH = 64
MAX_CATEGORICAL_TOKEN_LENGTH = 32
MAX_AMOUNT = 1_000_000.0
MAX_DESCRIPTION_LENGTH = 200
MAX_REASON_CODE_LENGTH = 64
MAX_TRIGGERED_SIGNALS = 64
MAX_WINDOW_FEATURES = 128
MAX_WINDOW_FEATURE_KEY_LENGTH = 64
WINDOW_FEATURE_VALUE_BOUND = 1_000_000.0
MAX_LATENCY_SECONDS = 60.0

# Deliberately narrow and explicit; extend only with an intentional change,
# never accept an arbitrary/unvalidated currency code.
ALLOWED_CURRENCIES = ("INR", "USD")

# Keeps event_time sane for a demo/test system without asserting anything
# about real-world calendar edge cases.
MIN_EVENT_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)
MAX_EVENT_TIME = datetime(2100, 1, 1, tzinfo=timezone.utc)

# Terms this package must never surface (see context.md "Canonical synthetic
# contract"). Checked case-insensitively against free-text fields.
_FORBIDDEN_TERMS = (
    "approve",
    "approved",
    "block",
    "blocked",
    "fraud_probability",
    "fraud probability",
    "razorpay risk score",
)

# --- Reusable field types -----------------------------------------------------

Outcome = Literal["success", "declined", "failed"]
Decision = Literal["below_review_threshold", "human_review", "unavailable_fail_closed"]
Currency = Literal["INR", "USD"]
DuplicateStatus = Literal["new", "duplicate"]
OrderingStatus = Literal["in_order", "late"]

# Opaque synthetic entity tokens such as ``syn_acct_001``. The mandatory
# ``syn_`` prefix and closed alphabet structurally reject realistic-looking
# PAN/IP/address/email/phone strings, which never take this shape.
EntityToken = Annotated[
    str,
    Field(
        min_length=len("syn_") + 1,
        max_length=MAX_ID_LENGTH,
        pattern=r"^syn_[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]

EventIdToken = Annotated[
    str,
    Field(min_length=len("evt_") + 1, max_length=MAX_ID_LENGTH, pattern=r"^evt_[a-z0-9_]{1,60}$"),
]

RequestIdToken = Annotated[
    str,
    Field(min_length=len("req_") + 1, max_length=MAX_ID_LENGTH, pattern=r"^req_[a-z0-9_]{1,60}$"),
]

# Categorical tokens such as country/region codes; not opaque identifiers,
# so no ``syn_`` prefix is required, but still bounded and closed-alphabet.
CategoricalToken = Annotated[
    str,
    Field(min_length=1, max_length=MAX_CATEGORICAL_TOKEN_LENGTH, pattern=r"^[A-Za-z0-9_]+$"),
]

AmountValue = Annotated[FiniteFloat, Field(gt=0.0, le=MAX_AMOUNT)]

# Stable, snake_case reason-code identifiers. The closed set of codes is
# defined by each feature module (added in later implementation steps); this
# layer only enforces the shared naming convention and length bound.
ReasonCode = Annotated[
    str,
    Field(min_length=1, max_length=MAX_REASON_CODE_LENGTH, pattern=r"^[a-z][a-z0-9_]*$"),
]

_WINDOW_FEATURE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _reject_forbidden_terms(text: str, *, field_name: str) -> None:
    lowered = text.lower()
    for term in _FORBIDDEN_TERMS:
        if term in lowered:
            raise ValueError(f"{field_name} must not contain the forbidden term {term!r}.")


# --- Base model ----------------------------------------------------------------


class _StrictSyntheticModel(BaseModel):
    """Shared strict, frozen, extra-forbidding base for this package's contracts."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# --- Event input ---------------------------------------------------------------


class SyntheticEvent(_StrictSyntheticModel):
    """A single artificial, opaque-token transaction-context event.

    Reject unknown fields (payment card numbers, CVV, full address, email,
    phone, user-agent, or literal raw IP address strings are never accepted
    because they are simply not part of this schema).
    """

    event_id: EventIdToken
    event_time: datetime
    account_id: EntityToken
    device_id: EntityToken
    payment_method_id: EntityToken
    merchant_id: EntityToken
    address_id: EntityToken
    ip_id: EntityToken
    amount: AmountValue
    currency: Currency
    outcome: Outcome
    account_country: CategoricalToken
    event_country: CategoricalToken
    event_region: CategoricalToken
    billing_shipping_match: bool
    vpn_or_proxy: bool
    retry_group_id: EntityToken | None = None

    @field_validator("event_time")
    @classmethod
    def _validate_event_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware.")
        if value < MIN_EVENT_TIME or value > MAX_EVENT_TIME:
            raise ValueError(
                f"event_time must be between {MIN_EVENT_TIME.isoformat()} "
                f"and {MAX_EVENT_TIME.isoformat()}."
            )
        return value

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        if value not in ALLOWED_CURRENCIES:
            raise ValueError(f"currency must be one of {ALLOWED_CURRENCIES}.")
        return value


# --- Derived output --------------------------------------------------------------


class TriggeredSignal(_StrictSyntheticModel):
    """One stable, explainable reason a synthetic signal fired."""

    reason_code: ReasonCode
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)]
    contribution: Annotated[float, Field(ge=0.0, le=1.0)]

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        _reject_forbidden_terms(value, field_name="description")
        return value

    @field_validator("reason_code")
    @classmethod
    def _validate_reason_code(cls, value: str) -> str:
        _reject_forbidden_terms(value, field_name="reason_code")
        return value


class SyntheticPlumbingResult(_StrictSyntheticModel):
    """Derived, non-decision-eligible output of the synthetic plumbing layer.

    ``context_signal_score`` is a transparent bounded heuristic, not a fraud
    probability and not the locked historical model's score. This result
    must never be merged with historical evaluation evidence.
    """

    schema_version: Literal["1.0"] = SYNTHETIC_SCHEMA_VERSION
    evidence_type: Literal["synthetic_plumbing_test"] = EVIDENCE_TYPE_SYNTHETIC_PLUMBING_TEST
    event_id: EventIdToken
    request_id: RequestIdToken
    decision: Decision
    context_signal_score: Annotated[float, Field(ge=0.0, le=1.0)]
    triggered_signals: Annotated[list[TriggeredSignal], Field(max_length=MAX_TRIGGERED_SIGNALS)] = (
        Field(default_factory=list)
    )
    window_features: dict[str, float] = Field(default_factory=dict)
    processed_at: datetime
    latency_seconds: Annotated[FiniteFloat, Field(ge=0.0, le=MAX_LATENCY_SECONDS)]
    duplicate_status: DuplicateStatus
    ordering_status: OrderingStatus

    @field_validator("processed_at")
    @classmethod
    def _validate_processed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("processed_at must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def _validate_window_features(self) -> SyntheticPlumbingResult:
        features = self.window_features
        if len(features) > MAX_WINDOW_FEATURES:
            raise ValueError(f"window_features must have at most {MAX_WINDOW_FEATURES} entries.")
        for key, value in features.items():
            if len(key) > MAX_WINDOW_FEATURE_KEY_LENGTH or not _WINDOW_FEATURE_KEY_PATTERN.match(
                key
            ):
                raise ValueError(f"window_features key {key!r} is not a valid snake_case name.")
            if not isinstance(value, float) or not math.isfinite(value):
                raise ValueError(f"window_features[{key!r}] must be a finite float.")
            if not -WINDOW_FEATURE_VALUE_BOUND <= value <= WINDOW_FEATURE_VALUE_BOUND:
                raise ValueError(f"window_features[{key!r}] is out of bounds.")
        return self
