"""Deterministic order-integrity verifier (synthetic reference).

A synthetic, deterministic pre-model order-integrity reference. It demonstrates
server-side amount reconstruction and invariant checking. It is not a live
Razorpay integration, not evidence about any real incident, and not part of
SecureSwipe's fraud-model metrics.

The lesson it exists to demonstrate: **never trust a client-supplied total.**
The client may send a SKU and a quantity, nothing else. The server reconstructs
every amount from a trusted catalog in integer minor units and compares.

This module never authorises payment, capture, refund, shipping, fulfilment,
approval, or blocking of any real transaction. It emits an integrity outcome for
downstream or manual handling and stops there.

Protocol: docs/evidence/MT7_ORDER_INTEGRITY_PROTOCOL.md
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping, Sequence

from src.order_integrity.catalog import (
    CATALOG_CURRENCY,
    CATALOG_VERSION,
    MAX_LINES_PER_CART,
    MAX_QUANTITY_PER_LINE,
    MAX_TOTAL_MINOR,
)

# -- outcomes -------------------------------------------------------------

Outcome = Literal[
    "integrity_verified_for_downstream_handling",
    "integrity_mismatch_review_required",
    "integrity_unavailable_fail_closed",
    "integrity_invalid_request",
]

VERIFIED: Outcome = "integrity_verified_for_downstream_handling"
MISMATCH: Outcome = "integrity_mismatch_review_required"
UNAVAILABLE: Outcome = "integrity_unavailable_fail_closed"
INVALID: Outcome = "integrity_invalid_request"

ALLOWED_OUTCOMES: tuple[Outcome, ...] = (VERIFIED, MISMATCH, UNAVAILABLE, INVALID)

#: Fields a client may send. Anything else is rejected, never ignored.
ALLOWED_CLIENT_LINE_FIELDS = frozenset({"sku", "quantity"})

#: Money-like and status-like fields a client must never supply.
FORBIDDEN_CLIENT_FIELDS = frozenset(
    {
        "price", "unit_price", "unitPrice", "amount", "amount_minor", "total",
        "total_amount", "totalAmount", "subtotal", "grand_total", "discount",
        "discount_amount", "tax", "tax_amount", "shipping", "shipping_cost",
        "currency", "payment_status", "paymentStatus", "status", "paid",
        "captured", "captured_amount", "fulfilment_status", "fulfillment_status",
    }
)


class OrderIntegrityError(ValueError):
    """Raised when a client request violates the input contract."""


# -- data structures ------------------------------------------------------


@dataclass(frozen=True)
class CartLine:
    """One synthetic cart line. Carries no monetary field by construction."""

    sku: str
    quantity: int


@dataclass(frozen=True)
class Quote:
    """A server-issued quote binding items, catalog version, currency, amount."""

    quote_id: str
    cart_digest: str
    catalog_version: str
    currency: str
    expected_amount_minor: int
    lines: tuple[CartLine, ...]
    issued_at_sequence: int
    expires_at_sequence: int


@dataclass(frozen=True)
class IntegrityResult:
    """Outcome for downstream or manual handling.

    Carries a reason code and bounded, non-sensitive detail only. It never
    contains a raw client payload, a secret, or a personal value.
    """

    outcome: Outcome
    reason_code: str
    quote_id: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.outcome not in ALLOWED_OUTCOMES:
            raise OrderIntegrityError(f"Outcome {self.outcome!r} is not allowlisted.")

    @property
    def fulfilment_eligible(self) -> bool:
        """True only for a verified outcome. Never authorises fulfilment itself."""
        return self.outcome == VERIFIED


# -- client input ---------------------------------------------------------


def parse_client_lines(payload: Sequence[Mapping[str, Any]]) -> tuple[CartLine, ...]:
    """Accept SKU and quantity only. Any money-like field is rejected.

    Rejecting rather than ignoring is deliberate: a silently dropped ``total``
    teaches a caller that sending one is acceptable.
    """
    if not isinstance(payload, (list, tuple)):
        raise OrderIntegrityError("Cart must be a list of lines.")
    if not payload:
        raise OrderIntegrityError("Cart must contain at least one line.")
    if len(payload) > MAX_LINES_PER_CART:
        raise OrderIntegrityError("Cart exceeds the maximum line count.")

    lines: list[CartLine] = []
    for raw in payload:
        if not isinstance(raw, Mapping):
            raise OrderIntegrityError("Each cart line must be an object.")
        supplied = set(raw)
        forbidden = supplied & FORBIDDEN_CLIENT_FIELDS
        if forbidden:
            raise OrderIntegrityError(
                f"Client-supplied field(s) rejected: {sorted(forbidden)}. "
                "The server reconstructs every amount."
            )
        unexpected = supplied - ALLOWED_CLIENT_LINE_FIELDS
        if unexpected:
            raise OrderIntegrityError(f"Unexpected field(s) rejected: {sorted(unexpected)}.")

        sku = raw.get("sku")
        quantity = raw.get("quantity")
        if not isinstance(sku, str) or not sku:
            raise OrderIntegrityError("Each line requires a string sku.")
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise OrderIntegrityError("Quantity must be an integer.")
        if quantity < 1:
            raise OrderIntegrityError("Quantity must be positive.")
        if quantity > MAX_QUANTITY_PER_LINE:
            raise OrderIntegrityError("Quantity exceeds the permitted bound.")
        lines.append(CartLine(sku=sku, quantity=quantity))

    # The bound applies to the MERGED quantity per SKU. Checking only per line
    # would let a caller split 200 units across three lines and slip past it.
    for sku, merged_quantity in canonical_cart(lines):
        if merged_quantity > MAX_QUANTITY_PER_LINE:
            raise OrderIntegrityError(
                "Merged quantity for a SKU exceeds the permitted bound."
            )
    return tuple(lines)


# -- canonicalisation and reconstruction ----------------------------------


def canonical_cart(lines: Iterable[CartLine]) -> tuple[tuple[str, int], ...]:
    """Deterministic cart form: quantities merged per SKU, sorted by SKU."""
    merged: dict[str, int] = {}
    for line in lines:
        merged[line.sku] = merged.get(line.sku, 0) + line.quantity
    return tuple(sorted(merged.items()))


def cart_digest(lines: Iterable[CartLine]) -> str:
    """SHA-256 over the canonical cart. Order and duplication cannot change it."""
    canonical = canonical_cart(lines)
    encoded = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def reconstruct_amount_minor(
    lines: Iterable[CartLine], catalog: Mapping[str, int] | None
) -> int:
    """Server-side amount in integer minor units.

    Every input is an integer and every operation is integer arithmetic, so no
    rounding or binary-floating-point error can arise.
    """
    if catalog is None:
        raise OrderIntegrityError("Trusted catalog is unavailable.")
    total = 0
    for sku, quantity in canonical_cart(lines):
        if sku not in catalog:
            raise OrderIntegrityError(f"SKU {sku!r} is not in the trusted catalog.")
        unit_minor = catalog[sku]
        if isinstance(unit_minor, bool) or not isinstance(unit_minor, int) or unit_minor < 0:
            raise OrderIntegrityError("Catalog prices must be non-negative integers.")
        if quantity < 1 or quantity > MAX_QUANTITY_PER_LINE:
            raise OrderIntegrityError("Quantity outside the permitted bound.")
        total += unit_minor * quantity
        if total > MAX_TOTAL_MINOR:
            raise OrderIntegrityError("Reconstructed total exceeds the permitted bound.")
    return total


def build_quote(
    *,
    quote_id: str,
    lines: Sequence[CartLine],
    catalog: Mapping[str, int] | None,
    catalog_version: str = CATALOG_VERSION,
    currency: str = CATALOG_CURRENCY,
    issued_at_sequence: int,
    validity_sequences: int = 10,
) -> Quote:
    """Issue a quote binding items, quantities, catalog version, currency, amount."""
    if not quote_id:
        raise OrderIntegrityError("quote_id is required.")
    expected = reconstruct_amount_minor(lines, catalog)
    return Quote(
        quote_id=quote_id,
        cart_digest=cart_digest(lines),
        catalog_version=catalog_version,
        currency=currency,
        expected_amount_minor=expected,
        lines=tuple(lines),
        issued_at_sequence=issued_at_sequence,
        expires_at_sequence=issued_at_sequence + validity_sequences,
    )


# -- confirmation ledger --------------------------------------------------


class ConfirmationLedger:
    """Minimal in-memory event ledger for the reference and its tests.

    Not a database, not durable, and not a production component. It exists so
    duplicate and out-of-order confirmations can be demonstrated deterministically.
    """

    def __init__(self) -> None:
        self._events: dict[str, IntegrityResult] = {}
        self._settled_quotes: set[str] = set()

    def seen(self, event_id: str) -> IntegrityResult | None:
        return self._events.get(event_id)

    def record(self, event_id: str, result: IntegrityResult) -> IntegrityResult:
        self._events[event_id] = result
        if result.outcome == VERIFIED and result.quote_id is not None:
            self._settled_quotes.add(result.quote_id)
        return result

    def is_settled(self, quote_id: str) -> bool:
        return quote_id in self._settled_quotes

    @property
    def event_count(self) -> int:
        return len(self._events)


# -- verification ---------------------------------------------------------


def verify_confirmation(
    *,
    quote: Quote | None,
    event_id: str,
    captured_amount_minor: Any,
    captured_currency: str,
    ledger: ConfirmationLedger,
    catalog: Mapping[str, int] | None,
    current_sequence: int,
    active_catalog_version: str = CATALOG_VERSION,
) -> IntegrityResult:
    """Verify a synthetic confirmation against a server-issued quote.

    Fails closed in every ambiguous case. Returns an outcome for downstream or
    manual handling; it authorises nothing.
    """
    if not event_id:
        return IntegrityResult(INVALID, "missing_event_id")

    # Idempotency: an identical event id replays its recorded outcome.
    previous = ledger.seen(event_id)
    if previous is not None:
        return previous

    if quote is None:
        return ledger.record(event_id, IntegrityResult(MISMATCH, "unknown_quote"))

    if catalog is None:
        return ledger.record(
            event_id, IntegrityResult(UNAVAILABLE, "trusted_catalog_unavailable",
                                      quote_id=quote.quote_id)
        )

    # A settled quote must not produce a second fulfilment-eligible outcome.
    if ledger.is_settled(quote.quote_id):
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "quote_already_settled",
                                      quote_id=quote.quote_id)
        )

    if current_sequence < quote.issued_at_sequence:
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "out_of_order_confirmation",
                                      quote_id=quote.quote_id)
        )
    if current_sequence > quote.expires_at_sequence:
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "expired_quote", quote_id=quote.quote_id)
        )
    if quote.catalog_version != active_catalog_version:
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "stale_catalog_version",
                                      quote_id=quote.quote_id)
        )
    if captured_currency != quote.currency:
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "currency_mismatch", quote_id=quote.quote_id)
        )
    if isinstance(captured_amount_minor, bool) or not isinstance(captured_amount_minor, int):
        return ledger.record(
            event_id, IntegrityResult(INVALID, "captured_amount_not_integer_minor_units",
                                      quote_id=quote.quote_id)
        )

    # Re-derive from the trusted catalog rather than trusting the stored quote.
    try:
        recomputed = reconstruct_amount_minor(quote.lines, catalog)
    except OrderIntegrityError:
        return ledger.record(
            event_id, IntegrityResult(UNAVAILABLE, "reconstruction_failed",
                                      quote_id=quote.quote_id)
        )

    if cart_digest(quote.lines) != quote.cart_digest:
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "quote_mutated_after_issue",
                                      quote_id=quote.quote_id)
        )
    if recomputed != quote.expected_amount_minor:
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "catalog_amount_changed",
                                      quote_id=quote.quote_id)
        )
    if captured_amount_minor != quote.expected_amount_minor:
        return ledger.record(
            event_id, IntegrityResult(MISMATCH, "amount_mismatch", quote_id=quote.quote_id)
        )

    return ledger.record(
        event_id,
        IntegrityResult(
            VERIFIED,
            "expected_quoted_and_captured_amounts_match",
            quote_id=quote.quote_id,
            detail={"amount_minor": recomputed, "currency": quote.currency},
        ),
    )


# -- optional synthetic signature verification ----------------------------


def sign_synthetic_body(raw_body: bytes, secret: bytes) -> str:
    """Test-only helper. Produces an HMAC-SHA256 hex digest over raw bytes."""
    return hmac.new(secret, raw_body, hashlib.sha256).hexdigest()


def verify_synthetic_signature(raw_body: bytes, signature: str, secret: bytes) -> bool:
    """Constant-time HMAC-SHA256 check over the **raw** bytes.

    Synthetic secrets only. This is not compatible with, and makes no claim
    about, any real webhook signing scheme.
    """
    if not isinstance(raw_body, (bytes, bytearray)):
        raise OrderIntegrityError("Signature must be verified over raw bytes.")
    expected = hmac.new(secret, bytes(raw_body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
