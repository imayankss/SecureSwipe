"""Deterministic Lane A serving-core feature builder.

Conservative by construction. It performs no fitting, no aggregation, no target
encoding, no history lookup, and no imputation. Each output row is a pure
function of one transaction row plus the presence or absence of its identity
record, so the builder holds no state across rows and cannot leak information
between them.

Missing data is preserved, never filled: missing categoricals become one
reserved token, missing numerics stay null. A real value equal to the reserved
token is a collision and is handled explicitly rather than silently merged into
the missing bucket.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping

from src.lane_a.serving_schema import (
    CATEGORICAL_FIELDS,
    IDENTITY_PRESENCE_FEATURE,
    IDENTITY_SOURCED_FIELDS,
    NUMERIC_FIELDS,
    SCHEMA_FIELD_NAMES,
    SOURCE_FIELD_NAMES,
    TRANSACTION_SOURCED_FIELDS,
    SchemaLockError,
    assert_schema_locked,
    is_forbidden,
)

RESERVED_MISSING = "__LANE_A_MISSING__"
ESCAPE_PREFIX = "__LANE_A_LITERAL__"
MISSING_TOKENS = frozenset({"", "NaN", "nan", "NA", "N/A", "null", "None"})

LABEL_NAMES = frozenset({"isFraud", "label", "target", "y"})


class FeatureBuildError(RuntimeError):
    """Raised when a row cannot be built without violating the contract."""


class ReservedTokenCollision(FeatureBuildError):
    """Raised when real data contains the reserved missing token."""


@dataclass(frozen=True)
class BuilderPolicy:
    """Declared, inspectable behaviour. Defaults fail closed."""

    on_reserved_collision: str = "reject"  # "reject" | "escape"

    def __post_init__(self) -> None:
        if self.on_reserved_collision not in {"reject", "escape"}:
            raise FeatureBuildError("on_reserved_collision must be 'reject' or 'escape'.")


def _normalise_categorical(field: str, raw: object, policy: BuilderPolicy) -> str:
    if raw is None:
        return RESERVED_MISSING
    value = str(raw).strip()
    if value in MISSING_TOKENS:
        return RESERVED_MISSING
    if value == RESERVED_MISSING:
        if policy.on_reserved_collision == "reject":
            raise ReservedTokenCollision(
                f"Column {field!r} contains a literal value equal to the reserved "
                "missing token; refusing to conflate real data with missingness."
            )
        return f"{ESCAPE_PREFIX}{value}"
    if value.startswith(ESCAPE_PREFIX):
        raise ReservedTokenCollision(
            f"Column {field!r} contains the escape prefix; refusing ambiguous encoding."
        )
    return value


def _normalise_numeric(field: str, raw: object) -> float | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if value in MISSING_TOKENS:
        return None
    try:
        number = float(value)
    except ValueError as exc:
        raise FeatureBuildError(f"Column {field!r} is not numeric.") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise FeatureBuildError(f"Column {field!r} must be finite.")
    if field == "TransactionAmt" and number < 0.0:
        raise FeatureBuildError("TransactionAmt must be non-negative.")
    return number


def _reject_forbidden(source_row: Mapping[str, object]) -> None:
    for name in source_row:
        if name in LABEL_NAMES:
            raise FeatureBuildError(
                f"Label column {name!r} was supplied to the feature builder; "
                "Lane A features are built without labels."
            )
    for name in TRANSACTION_SOURCED_FIELDS:
        if name not in source_row:
            raise FeatureBuildError(f"Required column {name!r} is absent from the row.")


def build_row(
    source_row: Mapping[str, object],
    *,
    identity_record_present: bool,
    device_type: object = None,
    policy: BuilderPolicy | None = None,
) -> dict[str, object]:
    """Build exactly the 13 locked features for one transaction.

    ``source_row`` must supply the eleven transaction-sourced columns.
    ``DeviceType`` is taken **only** from ``device_type``, and only when an
    identity record exists; any ``DeviceType`` key present in ``source_row`` is
    ignored, so a stray transaction-side value cannot bypass the identity join.
    """
    assert_schema_locked()
    effective_policy = policy or BuilderPolicy()
    if not isinstance(identity_record_present, bool):
        raise FeatureBuildError("identity_record_present must be a bool.")
    _reject_forbidden(source_row)

    built: dict[str, object] = {}
    for field in SOURCE_FIELD_NAMES:
        if field in IDENTITY_SOURCED_FIELDS:
            raw = device_type if identity_record_present else None
        else:
            raw = source_row[field]
        if field in NUMERIC_FIELDS:
            built[field] = _normalise_numeric(field, raw)
        elif field in CATEGORICAL_FIELDS:
            built[field] = _normalise_categorical(field, raw, effective_policy)
        else:  # pragma: no cover - guarded by the schema lock
            raise SchemaLockError(f"Unclassified field {field!r}.")
    built[IDENTITY_PRESENCE_FEATURE] = identity_record_present

    if tuple(built) != SCHEMA_FIELD_NAMES:
        raise SchemaLockError("Builder emitted a row that does not match the locked schema.")
    return built


def assert_selection_is_locked(names: Iterable[str]) -> None:
    """Reject any proposed input set that is not exactly the locked schema."""
    proposed = tuple(names)
    for name in proposed:
        if name in LABEL_NAMES:
            raise FeatureBuildError(f"{name!r} is a label and is never a model input.")
        if is_forbidden(name):
            raise FeatureBuildError(f"{name!r} is forbidden in the Lane A serving core.")
    if tuple(proposed) != SCHEMA_FIELD_NAMES:
        raise SchemaLockError(
            "Serving inputs must be exactly the locked 13-field schema, in order."
        )


def row_digest(rows: Iterable[Mapping[str, object]]) -> str:
    """Deterministic content digest over built rows. Publishable; rows are not."""
    digest = hashlib.sha256()
    for row in rows:
        if tuple(row) != SCHEMA_FIELD_NAMES:
            raise SchemaLockError("Cannot digest a row that violates the schema lock.")
        parts = []
        for field in SCHEMA_FIELD_NAMES:
            value = row[field]
            if value is None:
                parts.append("")
            elif isinstance(value, bool):
                parts.append("1" if value else "0")
            elif isinstance(value, float):
                parts.append(repr(value))
            else:
                parts.append(str(value))
        digest.update("\x1f".join(parts).encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Public wrappers added by the v2 amendment so variant builders can reuse the
# exact accepted normalisation rules rather than reimplementing them. Behaviour
# is unchanged; these delegate to the same private functions the locked
# 13-feature builder uses.
# ---------------------------------------------------------------------------


def normalise_categorical(field: str, raw: object, policy: BuilderPolicy | None = None) -> str:
    """Accepted categorical normalisation, including reserved-token protection."""
    return _normalise_categorical(field, raw, policy or BuilderPolicy())


def normalise_numeric(field: str, raw: object) -> float | None:
    """Accepted numeric normalisation. Missing stays None; never imputed here."""
    return _normalise_numeric(field, raw)
