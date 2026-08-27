"""Lane A (IEEE-CIS) feature-eligibility contract.

Every source column is classified into exactly one eligibility class. The
contract is declarative and label-free: it names no target, accepts no label as
a feature, and is safe to import without touching data.

Namespace isolation
-------------------
Lane A and Lane B (ULB) both contain columns literally named ``V1``..``V28``.
They are unrelated: Lane B's are PCA components, Lane A's are Vesta-engineered
aggregates. Raw names therefore collide by coincidence. Lane A model inputs are
consequently addressed by *qualified* name (``ieee_cis::V1``), which makes
separation structural rather than a naming convention that a rename could break.
This module imports nothing from Lane B.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

LANE = "A"
NAMESPACE = "ieee_cis"
QUALIFIER = "::"


class Eligibility(str, Enum):
    """Decision-time eligibility of a source column."""

    CANDIDATE_SNAPSHOT = "candidate_snapshot"
    BENCHMARK_ONLY = "benchmark_only"
    PROHIBITED = "prohibited"


class FeatureContractError(RuntimeError):
    """Raised when a feature selection violates the contract."""


@dataclass(frozen=True)
class FeatureRule:
    """One column's eligibility, with the reason recorded alongside it."""

    name: str
    family: str
    eligibility: Eligibility
    rationale: str
    optional: bool = False
    requires_point_in_time_proof: bool = False

    @property
    def qualified_name(self) -> str:
        return f"{NAMESPACE}{QUALIFIER}{self.name}"


def _rules() -> tuple[FeatureRule, ...]:
    rules: list[FeatureRule] = [
        FeatureRule(
            "isFraud",
            "label",
            Eligibility.PROHIBITED,
            "Target label. Never a feature, never read during partitioning or profiling.",
        ),
        FeatureRule(
            "TransactionID",
            "identifier",
            Eligibility.PROHIBITED,
            "Row identifier and identity join key. Carries no decision signal and is "
            "monotonic with time, so using it would leak ordering.",
        ),
        FeatureRule(
            "TransactionDT",
            "partition_key",
            Eligibility.PROHIBITED,
            "Frozen partition key. It is a relative offset that increases monotonically "
            "across the whole corpus, so as a raw feature it encodes each row's position "
            "relative to the frozen role boundaries. Derived point-in-time quantities "
            "(hour of day, day of week) may be proposed separately and are not covered "
            "by this rule.",
        ),
        FeatureRule(
            "TransactionAmt",
            "amount",
            Eligibility.CANDIDATE_SNAPSHOT,
            "Transaction amount is known at authorisation time.",
        ),
        FeatureRule(
            "ProductCD",
            "product",
            Eligibility.CANDIDATE_SNAPSHOT,
            "Product code is a property of the request itself.",
        ),
    ]
    rules += [
        FeatureRule(
            f"card{index}",
            "card",
            Eligibility.CANDIDATE_SNAPSHOT,
            "Card attribute presented with the authorisation request.",
        )
        for index in range(1, 7)
    ]
    rules += [
        FeatureRule(
            f"addr{index}",
            "address",
            Eligibility.CANDIDATE_SNAPSHOT,
            "Billing address attribute supplied with the request.",
        )
        for index in (1, 2)
    ]
    rules += [
        FeatureRule(
            f"dist{index}",
            "distance",
            Eligibility.BENCHMARK_ONLY,
            "Masked distance quantity. Its two endpoints and units are undocumented, so "
            "decision-time computability cannot be established.",
            requires_point_in_time_proof=True,
        )
        for index in (1, 2)
    ]
    rules += [
        FeatureRule(
            name,
            "email_domain",
            Eligibility.CANDIDATE_SNAPSHOT,
            "Email domain accompanies the request. Values are sensitive and must never "
            "be exported; only aggregate cardinality and missingness may be published.",
        )
        for name in ("P_emaildomain", "R_emaildomain")
    ]
    rules += [
        FeatureRule(
            f"C{index}",
            "count_aggregate",
            Eligibility.BENCHMARK_ONLY,
            "Documented only as a counting feature over entities associated with the "
            "card. The aggregation window and its anchor are not published, so it cannot "
            "be shown to exclude information created after the transaction.",
            requires_point_in_time_proof=True,
        )
        for index in range(1, 15)
    ]
    rules += [
        FeatureRule(
            f"D{index}",
            "timedelta",
            Eligibility.BENCHMARK_ONLY,
            "Documented only as a timedelta. Whether every instance looks strictly "
            "backwards from the transaction instant is not published.",
            requires_point_in_time_proof=True,
        )
        for index in range(1, 16)
    ]
    rules += [
        FeatureRule(
            f"M{index}",
            "match_flag",
            Eligibility.CANDIDATE_SNAPSHOT,
            "Match indicator between attributes presented in the same request, such as "
            "name-on-card against address. Computable from the request itself. "
            "Documentation is thin; revisit if primary docs contradict this.",
        )
        for index in range(1, 10)
    ]
    rules += [
        FeatureRule(
            f"V{index}",
            "vesta_engineered",
            Eligibility.BENCHMARK_ONLY,
            "Vendor-engineered aggregate covering ranking, counting and entity relations. "
            "Construction is masked, so point-in-time safety is unproven.",
            requires_point_in_time_proof=True,
        )
        for index in range(1, 340)
    ]
    rules += [
        FeatureRule(
            f"id_{index:02d}",
            "identity_signal",
            Eligibility.BENCHMARK_ONLY,
            "Identity signal with undocumented semantics; several are numeric with no "
            "published construction. Present for a minority of transactions.",
            optional=True,
            requires_point_in_time_proof=True,
        )
        for index in range(1, 39)
    ]
    rules += [
        FeatureRule(
            name,
            "device",
            Eligibility.CANDIDATE_SNAPSHOT,
            "Device attribute observable at request time. Optional: present only when an "
            "identity record exists. Values are sensitive and must never be exported.",
            optional=True,
        )
        for name in ("DeviceType", "DeviceInfo")
    ]
    return tuple(rules)


FEATURE_RULES: tuple[FeatureRule, ...] = _rules()
RULES_BY_NAME: Mapping[str, FeatureRule] = {rule.name: rule for rule in FEATURE_RULES}

LABEL_COLUMN = "isFraud"
PARTITION_KEY = "TransactionDT"
JOIN_KEY = "TransactionID"


def _names(eligibility: Eligibility) -> tuple[str, ...]:
    return tuple(rule.name for rule in FEATURE_RULES if rule.eligibility is eligibility)


def candidate_snapshot_features() -> tuple[str, ...]:
    """Columns plausibly available at transaction time."""
    return _names(Eligibility.CANDIDATE_SNAPSHOT)


def benchmark_only_features() -> tuple[str, ...]:
    """Columns usable offline but not serving-eligible without documentation."""
    return _names(Eligibility.BENCHMARK_ONLY)


def prohibited_features() -> tuple[str, ...]:
    """Columns that are never model inputs under any lane or mode."""
    return _names(Eligibility.PROHIBITED)


def optional_features() -> tuple[str, ...]:
    """Columns whose absence is meaningful and must be represented explicitly."""
    return tuple(rule.name for rule in FEATURE_RULES if rule.optional)


def serving_eligible_features() -> tuple[str, ...]:
    """The serving whitelist: candidates that need no further documentation.

    Anything flagged ``requires_point_in_time_proof`` is excluded by construction,
    so no ``C*``, ``D*`` or ``V*`` column can reach a served bundle through this
    function.
    """
    return tuple(
        rule.name
        for rule in FEATURE_RULES
        if rule.eligibility is Eligibility.CANDIDATE_SNAPSHOT
        and not rule.requires_point_in_time_proof
    )


def qualified(names: Iterable[str]) -> tuple[str, ...]:
    """Namespace-qualify Lane A column names for use as model inputs."""
    qualified_names = []
    for name in names:
        if name not in RULES_BY_NAME:
            raise FeatureContractError(f"{name!r} is not a Lane A column.")
        qualified_names.append(RULES_BY_NAME[name].qualified_name)
    return tuple(qualified_names)


def assert_disjoint_from(other_namespace_names: Iterable[str]) -> None:
    """Assert qualified Lane A inputs cannot collide with another lane's schema.

    Raw names are expected to collide (both lanes have ``V1``). Qualification is
    what makes the separation real, so this checks the qualified form.
    """
    other = set(other_namespace_names)
    collisions = {
        rule.qualified_name for rule in FEATURE_RULES if rule.qualified_name in other
    }
    if collisions:
        raise FeatureContractError(
            f"Qualified Lane A names collide with the supplied namespace: {sorted(collisions)}"
        )


def validate_selection(names: Iterable[str], *, for_serving: bool) -> tuple[str, ...]:
    """Validate a proposed feature selection, raising on any contract breach."""
    selected = tuple(names)
    if len(set(selected)) != len(selected):
        raise FeatureContractError("Duplicate column in selection.")
    for name in selected:
        rule = RULES_BY_NAME.get(name)
        if rule is None:
            raise FeatureContractError(f"{name!r} is not a Lane A column.")
        if rule.eligibility is Eligibility.PROHIBITED:
            raise FeatureContractError(
                f"{name!r} is prohibited as a model feature: {rule.rationale}"
            )
        if for_serving and rule.eligibility is not Eligibility.CANDIDATE_SNAPSHOT:
            raise FeatureContractError(
                f"{name!r} is {rule.eligibility.value} and is not serving-eligible."
            )
        if for_serving and rule.requires_point_in_time_proof:
            raise FeatureContractError(
                f"{name!r} needs primary documentation of point-in-time construction "
                "before it may be served."
            )
    return selected


def contract_summary() -> Mapping[str, object]:
    """Public-safe counts. Contains no data and no column values."""
    families: dict[str, dict[str, int]] = {}
    for rule in FEATURE_RULES:
        bucket = families.setdefault(rule.family, {})
        bucket[rule.eligibility.value] = bucket.get(rule.eligibility.value, 0) + 1
    return {
        "lane": LANE,
        "namespace": NAMESPACE,
        "total_columns": len(FEATURE_RULES),
        "candidate_snapshot": len(candidate_snapshot_features()),
        "benchmark_only": len(benchmark_only_features()),
        "prohibited": len(prohibited_features()),
        "serving_eligible": len(serving_eligible_features()),
        "optional": len(optional_features()),
        "requires_point_in_time_proof": sum(
            1 for rule in FEATURE_RULES if rule.requires_point_in_time_proof
        ),
        "by_family": families,
    }
