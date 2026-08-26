"""Lane A v2 feature variants.

A closed, predeclared set of five variants over columns the accepted MT3b
contract already classifies ``candidate_snapshot`` with no outstanding
point-in-time proof requirement. No other feature may be introduced here.

Every variant is validated against the contract at construction time, so a
variant cannot silently acquire an ineligible column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.lane_a.feature_contract import RULES_BY_NAME, Eligibility
from src.lane_a.serving_schema import IDENTITY_PRESENCE_FEATURE, SCHEMA_FIELD_NAMES

#: The 12 source fields of the accepted baseline, in accepted order.
BASE_SOURCE_FIELDS: tuple[str, ...] = tuple(
    name for name in SCHEMA_FIELD_NAMES if name != IDENTITY_PRESENCE_FEATURE
)

R_EMAIL: tuple[str, ...] = ("R_emaildomain",)
MATCH_FLAGS: tuple[str, ...] = tuple(f"M{index}" for index in range(1, 10))
DEVICE_INFO: tuple[str, ...] = ("DeviceInfo",)

#: Additions are categorical only. ``DeviceInfo`` is categorical text and is
#: never coerced to a number: the MT3b profile recorded it as mixed-type.
ADDITIONAL_CATEGORICAL: frozenset[str] = frozenset(R_EMAIL + MATCH_FLAGS + DEVICE_INFO)


#: Permanently prohibited in every variant, per the v2 amendment section 2.
#: Patterns are anchored on a numeric suffix so that ``DeviceInfo`` and
#: ``DeviceType`` are NOT caught by the ``D*`` family, and ``dist1``/``dist2``
#: are. ``serving_schema.is_forbidden`` is deliberately not reused here: it
#: encodes membership of the locked v1 13-field serving core, which is a
#: different question from decision-time eligibility for a candidate variant.
_PROHIBITED_EXACT: frozenset[str] = frozenset({"TransactionID", "isFraud", "TransactionDT"})
_PROHIBITED_FAMILIES: tuple[str, ...] = ("C", "D", "V", "dist", "id_")


def is_permanently_prohibited(name: str) -> bool:
    """True for columns no variant may ever contain."""
    if name in _PROHIBITED_EXACT:
        return True
    for family in _PROHIBITED_FAMILIES:
        if name.startswith(family) and name[len(family) :].isdigit():
            return True
    return False


class VariantError(RuntimeError):
    """Raised when a variant is malformed or contains an ineligible column."""


@dataclass(frozen=True)
class Variant:
    """One predeclared feature variant."""

    identifier: str
    name: str
    extra_fields: tuple[str, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        """Base source fields, then extras, then the derived boolean last."""
        return BASE_SOURCE_FIELDS + self.extra_fields + (IDENTITY_PRESENCE_FEATURE,)

    @property
    def input_count(self) -> int:
        return len(self.fields)


VARIANTS: tuple[Variant, ...] = (
    Variant("A", "base13", ()),
    Variant("B", "base_plus_r_email", R_EMAIL),
    Variant("C", "base_plus_match_flags", MATCH_FLAGS),
    Variant("D", "base_plus_email_and_match", R_EMAIL + MATCH_FLAGS),
    Variant("E", "full_candidate_snapshot", R_EMAIL + MATCH_FLAGS + DEVICE_INFO),
)

VARIANTS_BY_ID: Mapping[str, Variant] = {v.identifier: v for v in VARIANTS}

#: The union of every variant's fields; materialised once and subset per variant.
SUPERSET_FIELDS: tuple[str, ...] = VARIANTS_BY_ID["E"].fields

EXPECTED_INPUT_COUNTS: Mapping[str, int] = {"A": 13, "B": 14, "C": 22, "D": 23, "E": 24}


def validate_variant(variant: Variant) -> Variant:
    """Reject any variant containing a forbidden or non-eligible column."""
    fields = variant.fields
    if len(set(fields)) != len(fields):
        raise VariantError(f"Variant {variant.identifier} repeats a field.")
    for name in fields:
        if name == IDENTITY_PRESENCE_FEATURE:
            continue
        if is_permanently_prohibited(name):
            raise VariantError(f"{name!r} is permanently prohibited in every variant.")
        rule = RULES_BY_NAME.get(name)
        if rule is None:
            raise VariantError(f"{name!r} is not a Lane A source column.")
        if rule.eligibility is not Eligibility.CANDIDATE_SNAPSHOT:
            raise VariantError(
                f"{name!r} is {rule.eligibility.value}; only candidate_snapshot "
                "columns are eligible under the v2 amendment."
            )
        if rule.requires_point_in_time_proof:
            raise VariantError(f"{name!r} still requires point-in-time proof.")
    expected = EXPECTED_INPUT_COUNTS.get(variant.identifier)
    if expected is not None and variant.input_count != expected:
        raise VariantError(
            f"Variant {variant.identifier} has {variant.input_count} inputs, expected {expected}."
        )
    return variant


def validate_all() -> Mapping[str, int]:
    """Validate every variant and return the identifier-to-input-count map."""
    return {v.identifier: validate_variant(v).input_count for v in VARIANTS}


def choose_eligible_variant(
    eligible: tuple[str, ...] | list[str],
    results: Mapping[str, Mapping[str, Any]],
) -> str:
    """Apply the amendment's complete, deterministic variant-selection order.

    Average precision is primary. Exact ties resolve by fewer inputs, then the
    smaller serialized preprocessing/model artifact, then alphabetic variant
    identifier. An empty eligible set retains the accepted baseline.
    """
    if not eligible:
        return "A"
    unknown = set(eligible) - set(VARIANTS_BY_ID)
    if unknown:
        raise VariantError(f"Unknown eligible variant(s): {sorted(unknown)}")

    def key(identifier: str) -> tuple[float, int, int, str]:
        result = results[identifier]
        try:
            return (
                -float(result["average_precision"]),
                int(result["input_count"]),
                int(result["artifact_size_bytes"]),
                identifier,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise VariantError(f"Variant {identifier} lacks a valid selection result.") from exc

    return sorted(eligible, key=key)[0]


def categorical_fields(variant: Variant) -> tuple[str, ...]:
    """Categorical columns of a variant, including every v2 addition."""
    from src.lane_a.serving_schema import CATEGORICAL_FIELDS

    return tuple(
        name
        for name in variant.fields
        if name in CATEGORICAL_FIELDS or name in ADDITIONAL_CATEGORICAL
    )


def numeric_fields(variant: Variant) -> tuple[str, ...]:
    from src.lane_a.serving_schema import NUMERIC_FIELDS

    return tuple(name for name in variant.fields if name in NUMERIC_FIELDS)
