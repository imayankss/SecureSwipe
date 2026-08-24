"""Validation tests for the synthetic real-time event/output contracts.

All fixtures use obvious synthetic opaque tokens (``syn_*`` / ``evt_*`` /
``req_*``); nothing resembling a realistic PAN, IP address, or address
string is used anywhere in this file.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.synthetic_realtime.contracts import (
    EVIDENCE_TYPE_SYNTHETIC_PLUMBING_TEST,
    MAX_TRIGGERED_SIGNALS,
    MAX_WINDOW_FEATURES,
    SYNTHETIC_SCHEMA_VERSION,
    SyntheticEvent,
    SyntheticPlumbingResult,
    TriggeredSignal,
)

FIXED_EVENT_TIME = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
FIXED_PROCESSED_AT = FIXED_EVENT_TIME + timedelta(milliseconds=50)


def _valid_event_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "event_id": "evt_0000000001",
        "event_time": FIXED_EVENT_TIME,
        "account_id": "syn_acct_001",
        "device_id": "syn_dev_001",
        "payment_method_id": "syn_pm_001",
        "merchant_id": "syn_mer_001",
        "address_id": "syn_addr_001",
        "ip_id": "syn_ip_001",
        "amount": 499.5,
        "currency": "INR",
        "outcome": "success",
        "account_country": "IN",
        "event_country": "IN",
        "event_region": "APAC",
        "billing_shipping_match": True,
        "vpn_or_proxy": False,
        "retry_group_id": None,
    }
    kwargs.update(overrides)
    return kwargs


def _valid_result_kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "event_id": "evt_0000000001",
        "request_id": "req_0000000001",
        "decision": "below_review_threshold",
        "context_signal_score": 0.12,
        "triggered_signals": [],
        "window_features": {"velocity_1m_count": 1.0},
        "processed_at": FIXED_PROCESSED_AT,
        "latency_seconds": 0.004,
        "duplicate_status": "new",
        "ordering_status": "in_order",
    }
    kwargs.update(overrides)
    return kwargs


# --- SyntheticEvent ------------------------------------------------------------


def test_event_accepts_a_valid_synthetic_payload() -> None:
    event = SyntheticEvent(**_valid_event_kwargs())
    assert event.account_id == "syn_acct_001"
    assert event.event_time == FIXED_EVENT_TIME


def test_event_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(unexpected_field="x"))


@pytest.mark.parametrize("field", ["email", "phone", "pan", "cvv", "raw_ip", "user_agent"])
def test_event_rejects_sensitive_field_names(field: str) -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(**{field: "irrelevant"}))


def test_event_rejects_naive_event_time() -> None:
    naive_time = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(event_time=naive_time))


def test_event_rejects_out_of_range_event_time() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(event_time=datetime(1999, 1, 1, tzinfo=timezone.utc)))


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf")])
def test_event_rejects_non_finite_amount(amount: float) -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(amount=amount))


@pytest.mark.parametrize("amount", [0.0, -1.0, 1_000_001.0])
def test_event_rejects_out_of_range_amount(amount: float) -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(amount=amount))


def test_event_rejects_amount_as_string_under_strict_mode() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(amount="499.50"))


def test_event_entity_token_requires_syn_prefix() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(account_id="acct_001"))


def test_event_entity_token_rejects_realistic_ip_shaped_string() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(ip_id="192.168.1.1"))


def test_event_rejects_unallowed_currency() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(currency="XXX"))


def test_event_rejects_invalid_outcome() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(outcome="approved"))


def test_event_retry_group_id_accepts_none_and_valid_token() -> None:
    event_without = SyntheticEvent(**_valid_event_kwargs(retry_group_id=None))
    assert event_without.retry_group_id is None
    event_with = SyntheticEvent(**_valid_event_kwargs(retry_group_id="syn_retry_001"))
    assert event_with.retry_group_id == "syn_retry_001"


def test_event_retry_group_id_rejects_invalid_token() -> None:
    with pytest.raises(ValidationError):
        SyntheticEvent(**_valid_event_kwargs(retry_group_id="retry-001"))


def test_event_is_frozen() -> None:
    event = SyntheticEvent(**_valid_event_kwargs())
    with pytest.raises(ValidationError):
        event.amount = 1.0  # type: ignore[misc]


def test_two_events_from_identical_input_are_equal() -> None:
    first = SyntheticEvent(**_valid_event_kwargs())
    second = SyntheticEvent(**_valid_event_kwargs())
    assert first == second


# --- SyntheticPlumbingResult ---------------------------------------------------


def test_result_accepts_a_valid_payload_with_defaults() -> None:
    result = SyntheticPlumbingResult(**_valid_result_kwargs())
    assert result.schema_version == SYNTHETIC_SCHEMA_VERSION
    assert result.evidence_type == EVIDENCE_TYPE_SYNTHETIC_PLUMBING_TEST


@pytest.mark.parametrize("decision", ["approve", "approved", "block", "blocked", "pass"])
def test_result_rejects_non_canonical_decision_values(decision: str) -> None:
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(**_valid_result_kwargs(decision=decision))


def test_result_rejects_wrong_evidence_type() -> None:
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(**_valid_result_kwargs(evidence_type="genuine_demo_inference"))


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_result_rejects_context_signal_score_out_of_range(score: float) -> None:
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(**_valid_result_kwargs(context_signal_score=score))


def test_result_rejects_too_many_triggered_signals() -> None:
    signal = TriggeredSignal(
        reason_code="velocity_1m_count_high",
        description="Synthetic 1-minute count exceeded the illustrative baseline.",
        contribution=0.1,
    )
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(
            **_valid_result_kwargs(triggered_signals=[signal] * (MAX_TRIGGERED_SIGNALS + 1))
        )


@pytest.mark.parametrize(
    "term", ["approved", "Blocked", "fraud_probability", "Razorpay risk score"]
)
def test_triggered_signal_description_rejects_forbidden_terms(term: str) -> None:
    with pytest.raises(ValidationError):
        TriggeredSignal(
            reason_code="velocity_1m_count_high",
            description=f"This transaction was {term} by the synthetic layer.",
            contribution=0.1,
        )


def test_triggered_signal_reason_code_rejects_forbidden_terms() -> None:
    with pytest.raises(ValidationError):
        TriggeredSignal(
            reason_code="approved_by_synthetic_layer",
            description="Synthetic reason description.",
            contribution=0.1,
        )


def test_result_window_features_rejects_too_many_entries() -> None:
    too_many = {f"feature_{i}": 1.0 for i in range(MAX_WINDOW_FEATURES + 1)}
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(**_valid_result_kwargs(window_features=too_many))


def test_result_window_features_rejects_bad_key() -> None:
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(**_valid_result_kwargs(window_features={"Velocity-1m": 1.0}))


def test_result_window_features_rejects_non_finite_value() -> None:
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(
            **_valid_result_kwargs(window_features={"velocity_1m_count": float("nan")})
        )


def test_result_window_features_rejects_out_of_bounds_value() -> None:
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(
            **_valid_result_kwargs(window_features={"velocity_1m_count": 2_000_000.0})
        )


def test_result_rejects_negative_latency() -> None:
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(**_valid_result_kwargs(latency_seconds=-0.01))


def test_result_rejects_naive_processed_at() -> None:
    naive_time = datetime(2026, 8, 24, 12, 0, 0)  # noqa: DTZ001 - deliberately naive for this test
    with pytest.raises(ValidationError):
        SyntheticPlumbingResult(**_valid_result_kwargs(processed_at=naive_time))


def test_result_is_frozen() -> None:
    result = SyntheticPlumbingResult(**_valid_result_kwargs())
    with pytest.raises(ValidationError):
        result.decision = "human_review"  # type: ignore[misc]


def test_two_results_from_identical_input_are_equal() -> None:
    first = SyntheticPlumbingResult(**_valid_result_kwargs())
    second = SyntheticPlumbingResult(**_valid_result_kwargs())
    assert first == second
