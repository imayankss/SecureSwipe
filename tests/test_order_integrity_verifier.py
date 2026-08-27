"""Synthetic tests for the pre-model order-integrity reference.

A synthetic, deterministic pre-model order-integrity reference. It demonstrates
server-side amount reconstruction and invariant checking. It is not a live
Razorpay integration, not evidence about any real incident, and not part of
SecureSwipe's fraud-model metrics.

Every SKU, price, currency, event id, and secret here is synthetic. No network,
no credential, no model, no gateway.
"""

from __future__ import annotations

import random

import pytest

from src.order_integrity.catalog import (
    CATALOG,
    CATALOG_CURRENCY,
    CATALOG_NEXT,
    CATALOG_VERSION,
    CATALOG_VERSION_NEXT,
    MAX_QUANTITY_PER_LINE,
    MAX_TOTAL_MINOR,
    MINOR_UNITS_PER_MAJOR,
)
from src.order_integrity.verifier import (
    ALLOWED_OUTCOMES,
    FORBIDDEN_CLIENT_FIELDS,
    INVALID,
    MISMATCH,
    UNAVAILABLE,
    VERIFIED,
    CartLine,
    ConfirmationLedger,
    IntegrityResult,
    OrderIntegrityError,
    build_quote,
    canonical_cart,
    cart_digest,
    parse_client_lines,
    reconstruct_amount_minor,
    sign_synthetic_body,
    verify_confirmation,
    verify_synthetic_signature,
)

SECRET = b"synthetic-test-only-secret"


def _quote(lines=None, *, catalog=CATALOG, version=CATALOG_VERSION, seq=10, quote_id="Q1"):
    lines = lines or [CartLine("SKU_ALPHA", 2)]
    return build_quote(quote_id=quote_id, lines=lines, catalog=catalog,
                       catalog_version=version, issued_at_sequence=seq)


def _confirm(quote, **kwargs):
    params = dict(
        quote=quote,
        event_id=kwargs.pop("event_id", "EVT-1"),
        captured_amount_minor=kwargs.pop(
            "captured_amount_minor", quote.expected_amount_minor if quote else 0),
        captured_currency=kwargs.pop("captured_currency", CATALOG_CURRENCY),
        ledger=kwargs.pop("ledger", ConfirmationLedger()),
        catalog=kwargs.pop("catalog", CATALOG),
        current_sequence=kwargs.pop("current_sequence", 12),
    )
    params.update(kwargs)
    return verify_confirmation(**params)


# -- outcome vocabulary ---------------------------------------------------


def test_only_four_outcomes_exist_and_none_is_an_approval_word():
    assert ALLOWED_OUTCOMES == (
        "integrity_verified_for_downstream_handling",
        "integrity_mismatch_review_required",
        "integrity_unavailable_fail_closed",
        "integrity_invalid_request",
    )
    joined = " ".join(ALLOWED_OUTCOMES).lower()
    for banned in ("approved", "payment accepted", "fraudulent", "declined", "blocked"):
        assert banned not in joined


def test_unknown_outcome_is_refused():
    with pytest.raises(OrderIntegrityError, match="not allowlisted"):
        IntegrityResult("approved", "nope")  # type: ignore[arg-type]


# -- correct server-side reconstruction -----------------------------------


def test_server_reconstructs_the_amount_in_integer_minor_units():
    lines = parse_client_lines([{"sku": "SKU_ALPHA", "quantity": 2},
                                {"sku": "SKU_BETA", "quantity": 3}])
    expected = CATALOG["SKU_ALPHA"] * 2 + CATALOG["SKU_BETA"] * 3
    total = reconstruct_amount_minor(lines, CATALOG)
    assert total == expected
    assert isinstance(total, int)


def test_no_floating_point_currency_arithmetic_is_used():
    total = reconstruct_amount_minor([CartLine("SKU_GAMMA", 7)], CATALOG)
    assert isinstance(total, int) and not isinstance(total, float)


def test_happy_path_confirmation_verifies():
    quote = _quote()
    result = _confirm(quote)
    assert result.outcome == VERIFIED
    assert result.fulfilment_eligible is True
    assert result.detail["amount_minor"] == quote.expected_amount_minor


# -- client injection is rejected, not ignored ----------------------------


@pytest.mark.parametrize("field", sorted(FORBIDDEN_CLIENT_FIELDS))
def test_every_forbidden_client_field_is_rejected(field):
    with pytest.raises(OrderIntegrityError, match="rejected"):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": 1, field: 1}])


def test_client_total_is_rejected_not_silently_dropped():
    with pytest.raises(OrderIntegrityError, match="Client-supplied field"):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": 1, "total": 1}])


def test_unexpected_field_is_rejected():
    with pytest.raises(OrderIntegrityError, match="Unexpected field"):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": 1, "gift_note": "x"}])


# -- tampering ------------------------------------------------------------


def test_price_tampering_cannot_change_the_reconstructed_total():
    """A client 'price' never reaches arithmetic — it is refused at the door."""
    with pytest.raises(OrderIntegrityError):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": 1, "price": 1}])
    honest = reconstruct_amount_minor([CartLine("SKU_ALPHA", 1)], CATALOG)
    assert honest == CATALOG["SKU_ALPHA"]


def test_captured_amount_tampering_is_a_mismatch():
    quote = _quote()
    assert _confirm(quote, captured_amount_minor=1).outcome == MISMATCH
    assert _confirm(quote, captured_amount_minor=1).fulfilment_eligible is False


def test_quantity_tampering_changes_the_expected_amount():
    two = _quote(lines=[CartLine("SKU_ALPHA", 2)])
    three = _quote(lines=[CartLine("SKU_ALPHA", 3)], quote_id="Q2")
    assert three.expected_amount_minor != two.expected_amount_minor
    assert _confirm(two, captured_amount_minor=three.expected_amount_minor).outcome == MISMATCH


def test_major_unit_confusion_is_caught():
    """Paying 1,299 (major) against 129,900 (minor) must not verify."""
    quote = _quote(lines=[CartLine("SKU_ALPHA", 1)])
    major = quote.expected_amount_minor // MINOR_UNITS_PER_MAJOR
    assert _confirm(quote, captured_amount_minor=major).outcome == MISMATCH


def test_non_integer_captured_amount_is_invalid():
    quote = _quote()
    result = _confirm(quote, captured_amount_minor=1299.0)
    assert result.outcome == INVALID
    assert result.reason_code == "captured_amount_not_integer_minor_units"


def test_currency_mismatch_is_caught():
    quote = _quote()
    result = _confirm(quote, captured_currency="ZZZ")
    assert result.outcome == MISMATCH
    assert result.reason_code == "currency_mismatch"


# -- quote lifecycle ------------------------------------------------------


def test_unknown_quote_never_verifies():
    result = _confirm(None, captured_amount_minor=0)
    assert result.outcome == MISMATCH
    assert result.reason_code == "unknown_quote"
    assert result.fulfilment_eligible is False


def test_expired_quote_never_verifies():
    quote = _quote(seq=10)
    result = _confirm(quote, current_sequence=quote.expires_at_sequence + 1)
    assert result.outcome == MISMATCH
    assert result.reason_code == "expired_quote"


def test_stale_catalog_version_never_verifies():
    quote = _quote(version=CATALOG_VERSION)
    result = _confirm(quote, active_catalog_version=CATALOG_VERSION_NEXT)
    assert result.outcome == MISMATCH
    assert result.reason_code == "stale_catalog_version"


def test_catalog_price_change_after_quote_is_caught():
    """The amount is re-derived, so a repriced catalog cannot slip through."""
    quote = _quote(lines=[CartLine("SKU_ALPHA", 1)])
    result = _confirm(quote, catalog=CATALOG_NEXT)
    assert result.outcome == MISMATCH
    assert result.reason_code == "catalog_amount_changed"


def test_quote_mutated_after_issue_is_caught():
    quote = _quote(lines=[CartLine("SKU_ALPHA", 1)])
    tampered = type(quote)(
        quote_id=quote.quote_id, cart_digest=quote.cart_digest,
        catalog_version=quote.catalog_version, currency=quote.currency,
        expected_amount_minor=quote.expected_amount_minor,
        lines=(CartLine("SKU_ALPHA", 5),),   # items swapped, digest left stale
        issued_at_sequence=quote.issued_at_sequence,
        expires_at_sequence=quote.expires_at_sequence,
    )
    result = _confirm(tampered)
    assert result.outcome == MISMATCH
    assert result.reason_code in {"quote_mutated_after_issue", "catalog_amount_changed"}


# -- idempotency and ordering --------------------------------------------


def test_duplicate_event_id_is_idempotent():
    quote = _quote()
    ledger = ConfirmationLedger()
    first = _confirm(quote, ledger=ledger, event_id="EVT-DUP")
    second = _confirm(quote, ledger=ledger, event_id="EVT-DUP")
    assert first is second
    assert ledger.event_count == 1


def test_second_distinct_event_for_a_settled_quote_is_not_fulfilment_eligible():
    quote = _quote()
    ledger = ConfirmationLedger()
    assert _confirm(quote, ledger=ledger, event_id="EVT-A").outcome == VERIFIED
    second = _confirm(quote, ledger=ledger, event_id="EVT-B")
    assert second.outcome == MISMATCH
    assert second.reason_code == "quote_already_settled"
    assert second.fulfilment_eligible is False


def test_out_of_order_confirmation_fails_closed():
    quote = _quote(seq=10)
    result = _confirm(quote, current_sequence=9)
    assert result.outcome == MISMATCH
    assert result.reason_code == "out_of_order_confirmation"


def test_missing_event_id_is_invalid():
    assert _confirm(_quote(), event_id="").outcome == INVALID


# -- unavailable trusted state -------------------------------------------


def test_unavailable_catalog_fails_closed_at_confirmation():
    result = _confirm(_quote(), catalog=None)
    assert result.outcome == UNAVAILABLE
    assert result.fulfilment_eligible is False


def test_unavailable_catalog_refuses_to_build_a_quote():
    with pytest.raises(OrderIntegrityError, match="unavailable"):
        build_quote(quote_id="Q", lines=[CartLine("SKU_ALPHA", 1)], catalog=None,
                    issued_at_sequence=1)


def test_unknown_sku_is_refused():
    with pytest.raises(OrderIntegrityError, match="not in the trusted catalog"):
        reconstruct_amount_minor([CartLine("SKU_UNKNOWN", 1)], CATALOG)


# -- bounds and overflow safety ------------------------------------------


@pytest.mark.parametrize("quantity", [0, -1, -10_000])
def test_non_positive_quantity_is_refused(quantity):
    with pytest.raises(OrderIntegrityError, match="positive|integer"):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": quantity}])


def test_quantity_bound_is_enforced():
    with pytest.raises(OrderIntegrityError, match="bound"):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": MAX_QUANTITY_PER_LINE + 1}])


def test_boolean_is_not_accepted_as_a_quantity():
    with pytest.raises(OrderIntegrityError, match="integer"):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": True}])


def test_total_overflow_bound_is_enforced():
    huge = {"SKU_HUGE": MAX_TOTAL_MINOR}
    with pytest.raises(OrderIntegrityError, match="exceeds the permitted bound"):
        reconstruct_amount_minor([CartLine("SKU_HUGE", 2)], huge)


def test_cart_line_count_is_bounded():
    with pytest.raises(OrderIntegrityError, match="line count"):
        parse_client_lines([{"sku": "SKU_ALPHA", "quantity": 1} for _ in range(1_000)])


# -- deterministic canonicalisation --------------------------------------


def test_canonicalisation_merges_and_sorts():
    a = [CartLine("SKU_BETA", 1), CartLine("SKU_ALPHA", 2), CartLine("SKU_BETA", 2)]
    b = [CartLine("SKU_ALPHA", 2), CartLine("SKU_BETA", 3)]
    assert canonical_cart(a) == canonical_cart(b) == (("SKU_ALPHA", 2), ("SKU_BETA", 3))
    assert cart_digest(a) == cart_digest(b)


def test_digest_changes_when_quantities_change():
    assert cart_digest([CartLine("SKU_ALPHA", 2)]) != cart_digest([CartLine("SKU_ALPHA", 3)])


def test_reconstruction_is_deterministic():
    lines = [CartLine("SKU_ALPHA", 2), CartLine("SKU_GAMMA", 1)]
    assert reconstruct_amount_minor(lines, CATALOG) == reconstruct_amount_minor(lines, CATALOG)


# -- property-style: client prices cannot influence the total -------------


def test_property_client_price_fields_can_never_influence_the_total():
    """Across many generated synthetic carts, injected price-like fields either
    are refused outright or leave the server total unchanged."""
    rng = random.Random(42)
    skus = list(CATALOG)
    for _ in range(300):
        chosen = rng.sample(skus, rng.randint(1, len(skus)))
        lines = [
            {"sku": sku, "quantity": rng.randint(1, MAX_QUANTITY_PER_LINE)}
            for sku in chosen
        ]
        honest_total = reconstruct_amount_minor(parse_client_lines(lines), CATALOG)

        poisoned = [dict(line) for line in lines]
        field = rng.choice(sorted(FORBIDDEN_CLIENT_FIELDS))
        poisoned[rng.randrange(len(poisoned))][field] = rng.choice([0, 1, -5, 999_999_999])
        with pytest.raises(OrderIntegrityError):
            parse_client_lines(poisoned)

        # Stripping the injected field reproduces exactly the honest total.
        stripped = [{k: v for k, v in line.items() if k in {"sku", "quantity"}}
                    for line in poisoned]
        assert reconstruct_amount_minor(parse_client_lines(stripped), CATALOG) == honest_total


# -- synthetic signature verification ------------------------------------


def test_raw_body_signature_round_trip():
    body = b'{"event_id":"EVT-1","quote_id":"Q1"}'
    assert verify_synthetic_signature(body, sign_synthetic_body(body, SECRET), SECRET)


def test_tampered_body_signature_is_rejected():
    body = b'{"event_id":"EVT-1","quote_id":"Q1"}'
    signature = sign_synthetic_body(body, SECRET)
    assert not verify_synthetic_signature(body + b" ", signature, SECRET)


def test_wrong_secret_is_rejected():
    body = b'{"event_id":"EVT-1"}'
    assert not verify_synthetic_signature(body, sign_synthetic_body(body, SECRET), b"other")


def test_signature_requires_raw_bytes():
    with pytest.raises(OrderIntegrityError, match="raw bytes"):
        verify_synthetic_signature("a string", "deadbeef", SECRET)  # type: ignore[arg-type]


def test_signature_uses_constant_time_comparison():
    import inspect

    from src.order_integrity import verifier

    source = inspect.getsource(verifier.verify_synthetic_signature)
    assert "compare_digest" in source
    assert "==" not in source.split("return")[-1]


# -- output privacy -------------------------------------------------------


def test_result_objects_carry_no_raw_payload_or_secret():
    quote = _quote()
    for result in (
        _confirm(quote),
        _confirm(quote, captured_amount_minor=1, event_id="E2"),
        _confirm(quote, catalog=None, event_id="E3"),
        _confirm(None, event_id="E4", captured_amount_minor=0),
    ):
        rendered = f"{result.outcome} {result.reason_code} {result.detail}".lower()
        for forbidden in ("secret", "password", "card", "cvv", "email", "/users/",
                          "sku_", "token"):
            assert forbidden not in rendered
        assert set(result.detail) <= {"amount_minor", "currency"}


def test_module_makes_no_model_or_network_call():
    import inspect

    from src.order_integrity import catalog, verifier

    import ast

    for module in (verifier, catalog):
        tree = ast.parse(inspect.getsource(module))
        # Drop docstrings: the mandated framing text legitimately says
        # "not a live Razorpay integration", which is a disclaimer, not a call.
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)) and ast.get_docstring(node):
                node.body = node.body[1:]
        code = ast.unparse(tree).lower()
        for forbidden in ("requests", "httpx", "urllib", "socket", "predict",
                          "model_service", "threshold", "sqlite3", "razorpay"):
            assert forbidden not in code, f"{module.__name__} references {forbidden}"


def test_merged_quantity_bound_cannot_be_bypassed_by_splitting_lines():
    """Regression: a per-line cap alone would let 300 units through as 3x100."""
    split = [{"sku": "SKU_ALPHA", "quantity": MAX_QUANTITY_PER_LINE} for _ in range(3)]
    with pytest.raises(OrderIntegrityError, match="Merged quantity"):
        parse_client_lines(split)
