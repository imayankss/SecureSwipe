"""The locked Lane A serving-core schema.

Thirteen model inputs: twelve source columns drawn from the MT3b
``candidate_snapshot`` set, plus one derived boolean recording whether an
identity record existed for the transaction.

The schema is a *lock*, not a suggestion. Everything outside it is forbidden,
including every column the MT3b contract classified ``benchmark_only`` and every
Lane B column name. Widening it is a protocol amendment, not a code change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.lane_a.feature_contract import (
    NAMESPACE,
    QUALIFIER,
    RULES_BY_NAME,
    Eligibility,
    FeatureContractError,
)


class SchemaLockError(RuntimeError):
    """Raised when the locked serving schema would be violated."""


@dataclass(frozen=True)
class SchemaField:
    """One locked model input."""

    name: str
    kind: str  # "numeric" | "categorical" | "boolean"
    derived: bool = False
    optional: bool = False

    @property
    def qualified_name(self) -> str:
        return f"{NAMESPACE}{QUALIFIER}{self.name}"


IDENTITY_PRESENCE_FEATURE = "identity_record_present"

SERVING_CORE_SCHEMA: tuple[SchemaField, ...] = (
    SchemaField("TransactionAmt", "numeric"),
    SchemaField("ProductCD", "categorical"),
    SchemaField("card1", "numeric"),
    SchemaField("card2", "numeric"),
    SchemaField("card3", "numeric"),
    SchemaField("card4", "categorical"),
    SchemaField("card5", "numeric"),
    SchemaField("card6", "categorical"),
    SchemaField("addr1", "numeric"),
    SchemaField("addr2", "numeric"),
    SchemaField("P_emaildomain", "categorical"),
    SchemaField("DeviceType", "categorical", optional=True),
    SchemaField(IDENTITY_PRESENCE_FEATURE, "boolean", derived=True),
)

SCHEMA_FIELD_NAMES: tuple[str, ...] = tuple(field.name for field in SERVING_CORE_SCHEMA)
SOURCE_FIELD_NAMES: tuple[str, ...] = tuple(
    field.name for field in SERVING_CORE_SCHEMA if not field.derived
)
# DeviceType is a source column but arrives through the identity left-join, not
# from the transaction row. Splitting the two makes the join boundary explicit.
IDENTITY_SOURCED_FIELDS: tuple[str, ...] = ("DeviceType",)
TRANSACTION_SOURCED_FIELDS: tuple[str, ...] = tuple(
    name for name in SOURCE_FIELD_NAMES if name not in IDENTITY_SOURCED_FIELDS
)
CATEGORICAL_FIELDS: tuple[str, ...] = tuple(
    field.name for field in SERVING_CORE_SCHEMA if field.kind == "categorical"
)
NUMERIC_FIELDS: tuple[str, ...] = tuple(
    field.name for field in SERVING_CORE_SCHEMA if field.kind == "numeric"
)
QUALIFIED_SCHEMA: tuple[str, ...] = tuple(
    field.qualified_name for field in SERVING_CORE_SCHEMA
)

# Named explicitly so a test can assert each one is rejected rather than merely
# absent. Absence could be an oversight; explicit rejection cannot.
FORBIDDEN_EXACT: frozenset[str] = frozenset(
    {"TransactionID", "isFraud", "TransactionDT", "R_emaildomain", "DeviceInfo"}
)
FORBIDDEN_PREFIXES: tuple[str, ...] = ("M", "C", "D", "V", "dist", "id_")


def is_forbidden(name: str) -> bool:
    """True when a column may never enter the Lane A serving core."""
    if name in SCHEMA_FIELD_NAMES:
        return False
    if name in FORBIDDEN_EXACT:
        return True
    for prefix in FORBIDDEN_PREFIXES:
        if name.startswith(prefix):
            return True
    return name not in SCHEMA_FIELD_NAMES


def assert_schema_locked() -> None:
    """Verify the lock's internal invariants at import or test time."""
    if len(SERVING_CORE_SCHEMA) != 13:
        raise SchemaLockError(
            f"Serving core must hold exactly 13 inputs, found {len(SERVING_CORE_SCHEMA)}."
        )
    if len(set(SCHEMA_FIELD_NAMES)) != len(SCHEMA_FIELD_NAMES):
        raise SchemaLockError("Duplicate field in the serving core.")
    derived = [field for field in SERVING_CORE_SCHEMA if field.derived]
    if [field.name for field in derived] != [IDENTITY_PRESENCE_FEATURE]:
        raise SchemaLockError("Exactly one derived field is permitted.")
    for field in SERVING_CORE_SCHEMA:
        if field.derived:
            continue
        rule = RULES_BY_NAME.get(field.name)
        if rule is None:
            raise SchemaLockError(f"{field.name!r} is not a Lane A source column.")
        if rule.eligibility is not Eligibility.CANDIDATE_SNAPSHOT:
            raise SchemaLockError(
                f"{field.name!r} is {rule.eligibility.value}; only candidate_snapshot "
                "columns may be served."
            )
        if rule.requires_point_in_time_proof:
            raise SchemaLockError(f"{field.name!r} still requires point-in-time proof.")
        if is_forbidden(field.name):
            raise SchemaLockError(f"{field.name!r} is on the forbidden list.")


def assert_no_lane_b_names(lane_b_names: object) -> None:
    """Reject any attempt to admit a Lane B column name into the serving core.

    Lane B and Lane A both contain ``V1``..``V28``; qualification keeps the model
    input namespaces apart, and no Lane B raw name is a Lane A serving field.
    """
    try:
        names = set(lane_b_names)  # type: ignore[call-overload]
    except TypeError as exc:  # pragma: no cover - defensive
        raise SchemaLockError("lane_b_names must be iterable.") from exc
    intruders = names & set(SCHEMA_FIELD_NAMES)
    if intruders:
        raise SchemaLockError(
            f"Lane B names must never appear in the Lane A serving core: {sorted(intruders)}"
        )
    qualified_intruders = names & set(QUALIFIED_SCHEMA)
    if qualified_intruders:
        raise SchemaLockError(f"Qualified name collision: {sorted(qualified_intruders)}")


def validate_against_contract() -> Mapping[str, object]:
    """Cross-check the lock against the MT3b contract and return a safe summary."""
    assert_schema_locked()
    from src.lane_a.feature_contract import validate_selection

    try:
        validate_selection(SOURCE_FIELD_NAMES, for_serving=True)
    except FeatureContractError as exc:  # pragma: no cover - guarded by the lock
        raise SchemaLockError(str(exc)) from exc
    return {
        "lane": "A",
        "namespace": NAMESPACE,
        "model_inputs": len(SERVING_CORE_SCHEMA),
        "source_fields": len(SOURCE_FIELD_NAMES),
        "derived_fields": 1,
        "categorical_fields": len(CATEGORICAL_FIELDS),
        "numeric_fields": len(NUMERIC_FIELDS),
        "optional_fields": sum(1 for f in SERVING_CORE_SCHEMA if f.optional),
    }
