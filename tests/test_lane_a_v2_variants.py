"""Synthetic-only tests for Lane A v2 variants and the capacity policy.

Nothing here reads the IEEE-CIS CSVs, the private artifacts, any label, or any
real row. Every fixture is constructed in-process.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.lane_a.capacity import (
    BELOW_REVIEW_THRESHOLD,
    DECISIONS,
    HUMAN_REVIEW,
    ILLUSTRATIVE_CAPACITY_TIERS,
    POLICY_VERSION,
    UNAVAILABLE_FAIL_CLOSED,
    CapacityPolicyError,
    MerchantCapacityConfig,
    allocate_reviews,
    frontier_row,
    workload_for_recall,
)
from src.lane_a.feature_builder import (
    RESERVED_MISSING,
    ReservedTokenCollision,
    normalise_categorical,
)
from src.lane_a.serving_schema import IDENTITY_PRESENCE_FEATURE, SCHEMA_FIELD_NAMES
from src.lane_a.variants import (
    EXPECTED_INPUT_COUNTS,
    SUPERSET_FIELDS,
    VARIANTS,
    VARIANTS_BY_ID,
    VariantError,
    Variant,
    categorical_fields,
    choose_eligible_variant,
    is_permanently_prohibited,
    numeric_fields,
    validate_all,
    validate_variant,
)

# ------------------------------------------------ variant composition


def test_every_variant_has_exactly_its_declared_feature_count() -> None:
    assert validate_all() == EXPECTED_INPUT_COUNTS
    assert EXPECTED_INPUT_COUNTS == {"A": 13, "B": 14, "C": 22, "D": 23, "E": 24}


def test_variant_a_is_exactly_the_accepted_baseline() -> None:
    assert VARIANTS_BY_ID["A"].fields == SCHEMA_FIELD_NAMES


@pytest.mark.parametrize(
    ("identifier", "expected_extra"),
    [
        ("B", ("R_emaildomain",)),
        ("C", tuple(f"M{i}" for i in range(1, 10))),
        ("D", ("R_emaildomain", *[f"M{i}" for i in range(1, 10)])),
        ("E", ("R_emaildomain", *[f"M{i}" for i in range(1, 10)], "DeviceInfo")),
    ],
)
def test_variants_add_exactly_the_declared_columns(identifier, expected_extra) -> None:
    variant = VARIANTS_BY_ID[identifier]
    assert variant.extra_fields == expected_extra
    assert set(variant.fields) - set(SCHEMA_FIELD_NAMES) == set(expected_extra)


def test_derived_boolean_is_last_in_every_variant() -> None:
    for variant in VARIANTS:
        assert variant.fields[-1] == IDENTITY_PRESENCE_FEATURE
        assert variant.fields.count(IDENTITY_PRESENCE_FEATURE) == 1


def test_superset_is_the_union_of_all_variants() -> None:
    union: set[str] = set()
    for variant in VARIANTS:
        union |= set(variant.fields)
    assert union == set(SUPERSET_FIELDS)
    assert len(SUPERSET_FIELDS) == 24


def test_every_variant_is_a_subset_of_the_superset() -> None:
    for variant in VARIANTS:
        assert set(variant.fields) <= set(SUPERSET_FIELDS)


# ------------------------------------------------ prohibited features


@pytest.mark.parametrize(
    "name",
    [
        "TransactionID",
        "isFraud",
        "TransactionDT",
        "C1",
        "C14",
        "D1",
        "D15",
        "V1",
        "V339",
        "dist1",
        "dist2",
        "id_01",
        "id_38",
    ],
)
def test_prohibited_fields_are_rejected(name: str) -> None:
    assert is_permanently_prohibited(name)
    with pytest.raises(VariantError):
        validate_variant(Variant("X", "bad", (name,)))


@pytest.mark.parametrize("name", ["DeviceInfo", "DeviceType", "M1", "R_emaildomain"])
def test_device_and_match_columns_are_not_caught_by_the_prefix_families(name: str) -> None:
    """DeviceInfo/DeviceType must not be swept up by the ``D*`` family."""
    assert not is_permanently_prohibited(name)


def test_no_variant_contains_a_prohibited_field() -> None:
    for variant in VARIANTS:
        for name in variant.fields:
            if name == IDENTITY_PRESENCE_FEATURE:
                continue
            assert not is_permanently_prohibited(name)


def test_labels_and_identifiers_cannot_enter_a_variant() -> None:
    for bad in ("isFraud", "TransactionID"):
        with pytest.raises(VariantError):
            validate_variant(Variant("X", "bad", (bad,)))


def test_benchmark_only_column_is_refused_even_though_it_exists() -> None:
    with pytest.raises(VariantError):
        validate_variant(Variant("X", "bad", ("C1",)))


def test_duplicate_field_is_refused() -> None:
    with pytest.raises(VariantError):
        validate_variant(Variant("X", "dup", ("R_emaildomain", "R_emaildomain")))


def test_declared_count_mismatch_is_refused() -> None:
    with pytest.raises(VariantError):
        validate_variant(Variant("A", "wrong_size", ("R_emaildomain",)))


# ------------------------------------------------ typing of additions


def test_device_info_is_categorical_text_and_never_numeric() -> None:
    variant = VARIANTS_BY_ID["E"]
    assert "DeviceInfo" in categorical_fields(variant)
    assert "DeviceInfo" not in numeric_fields(variant)


def test_match_flags_and_r_email_are_categorical() -> None:
    variant = VARIANTS_BY_ID["D"]
    categorical = set(categorical_fields(variant))
    assert "R_emaildomain" in categorical
    assert {f"M{i}" for i in range(1, 10)} <= categorical


def test_numeric_fields_are_unchanged_across_variants() -> None:
    baseline = numeric_fields(VARIANTS_BY_ID["A"])
    for variant in VARIANTS:
        assert numeric_fields(variant) == baseline
        assert len(baseline) == 7


def test_variant_selection_uses_every_predeclared_tie_break() -> None:
    results = {
        "B": {"average_precision": 0.30, "input_count": 14, "artifact_size_bytes": 500},
        "C": {"average_precision": 0.31, "input_count": 22, "artifact_size_bytes": 400},
        "D": {"average_precision": 0.31, "input_count": 23, "artifact_size_bytes": 300},
        "E": {"average_precision": 0.31, "input_count": 22, "artifact_size_bytes": 600},
    }
    assert choose_eligible_variant(["B", "C", "D", "E"], results) == "C"

    results["E"]["artifact_size_bytes"] = 300
    assert choose_eligible_variant(["C", "E"], results) == "E"

    results["C"]["artifact_size_bytes"] = 300
    assert choose_eligible_variant(["C", "E"], results) == "C"


def test_variant_selection_retains_baseline_when_none_are_eligible() -> None:
    assert choose_eligible_variant([], {}) == "A"


# ------------------------------------------------ missing / collisions


@pytest.mark.parametrize("token", ["", "  ", "NaN", "NA", "null", "None"])
def test_missing_categoricals_are_deterministic_across_added_fields(token: str) -> None:
    for field in ("R_emaildomain", "M1", "DeviceInfo"):
        assert normalise_categorical(field, token) == RESERVED_MISSING


def test_reserved_token_collision_fails_closed_on_added_fields() -> None:
    for field in ("R_emaildomain", "M5", "DeviceInfo"):
        with pytest.raises(ReservedTokenCollision):
            normalise_categorical(field, RESERVED_MISSING)


def test_device_info_mixed_values_are_kept_as_text() -> None:
    assert normalise_categorical("DeviceInfo", "12345") == "12345"
    assert normalise_categorical("DeviceInfo", "build_alpha") == "build_alpha"


# ------------------------------------------------ capacity policy


def test_review_budget_is_floor_of_capacity_times_days() -> None:
    config = MerchantCapacityConfig(daily_review_capacity=100, evaluation_period_days=22.1988)
    assert config.review_budget == 2219  # floor(2219.88)


def test_budget_allocates_to_the_highest_scores_first() -> None:
    scores = np.array([0.1, 0.9, 0.5, 0.7])
    config = MerchantCapacityConfig(daily_review_capacity=2, evaluation_period_days=1.0)
    result = allocate_reviews(scores, config)
    assert result["selected_count"] == 2
    selected = np.asarray(result["selected_mask"], dtype=bool)
    assert list(selected) == [False, True, False, True]


def test_ties_resolve_by_stable_source_position() -> None:
    scores = np.array([0.5, 0.5, 0.5, 0.5])
    config = MerchantCapacityConfig(daily_review_capacity=2, evaluation_period_days=1.0)
    result = allocate_reviews(scores, config)
    selected = np.asarray(result["selected_mask"], dtype=bool)
    assert list(selected) == [True, True, False, False]
    assert "stable source position" in str(result["tie_handling"])


def test_allocation_is_deterministic_across_repeated_calls() -> None:
    rng = np.random.default_rng(3)
    scores = rng.random(500)
    config = MerchantCapacityConfig(daily_review_capacity=50, evaluation_period_days=2.0)
    first = allocate_reviews(scores, config)["selected_mask"]
    second = allocate_reviews(scores, config)["selected_mask"]
    assert np.array_equal(first, second)


def test_budget_larger_than_population_is_capped() -> None:
    scores = np.array([0.1, 0.2, 0.3])
    config = MerchantCapacityConfig(daily_review_capacity=1000, evaluation_period_days=10.0)
    result = allocate_reviews(scores, config)
    assert result["selected_count"] == 3


def test_only_bounded_decision_vocabulary_is_emitted() -> None:
    scores = np.array([0.9, 0.1])
    config = MerchantCapacityConfig(daily_review_capacity=1, evaluation_period_days=1.0)
    decisions = set(allocate_reviews(scores, config)["decisions"])
    assert decisions <= set(DECISIONS)
    assert decisions <= {HUMAN_REVIEW, BELOW_REVIEW_THRESHOLD}


def test_unavailable_scores_fail_closed() -> None:
    config = MerchantCapacityConfig(daily_review_capacity=10, evaluation_period_days=1.0)
    result = allocate_reviews([], config, scores_available=False)
    assert result["decision_for_all"] == UNAVAILABLE_FAIL_CLOSED
    assert result["selected_count"] == 0


def test_policy_never_emits_an_approval_or_block_term() -> None:
    forbidden = {"approve", "approved", "block", "blocked", "decline", "declined", "pass"}
    assert not (set(DECISIONS) & forbidden)
    assert POLICY_VERSION == "lane_a_capacity_policy_v2"


@pytest.mark.parametrize("bad", [-1, 0.5, True])
def test_invalid_capacity_is_refused(bad: object) -> None:
    with pytest.raises(CapacityPolicyError):
        MerchantCapacityConfig(daily_review_capacity=bad, evaluation_period_days=1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0.0, -1.0, float("inf")])
def test_invalid_period_is_refused(bad: float) -> None:
    with pytest.raises(CapacityPolicyError):
        MerchantCapacityConfig(daily_review_capacity=10, evaluation_period_days=bad)


def test_non_finite_scores_are_refused() -> None:
    config = MerchantCapacityConfig(daily_review_capacity=1, evaluation_period_days=1.0)
    with pytest.raises(CapacityPolicyError):
        allocate_reviews(np.array([0.1, np.nan]), config)


# ------------------------------------------------ frontier arithmetic


def test_frontier_confusion_counts_reconcile_exactly() -> None:
    rng = np.random.default_rng(11)
    labels = (rng.random(1000) < 0.1).astype(int)
    scores = rng.random(1000)
    config = MerchantCapacityConfig(daily_review_capacity=50, evaluation_period_days=2.0)
    row = frontier_row(labels, scores, config)
    assert row["tp"] + row["fp"] + row["fn"] + row["tn"] == 1000
    assert row["alerts_selected"] == row["tp"] + row["fp"]
    assert row["alerts_selected"] == min(config.review_budget, 1000)


def test_frontier_row_carries_the_illustrative_label() -> None:
    labels = np.array([1, 0, 1, 0])
    scores = np.array([0.9, 0.8, 0.7, 0.6])
    row = frontier_row(labels, scores, MerchantCapacityConfig(2, 1.0))
    assert "not Razorpay economics" in str(row["label"])
    assert "not a universal merchant policy" in str(row["label"])


def test_workload_for_recall_is_a_reference_not_a_default() -> None:
    labels = np.array([1] * 10 + [0] * 90)
    scores = np.concatenate([np.linspace(0.99, 0.9, 10), np.linspace(0.5, 0.1, 90)])
    result = workload_for_recall(labels, scores, evaluation_period_days=1.0)
    assert result["reachable"] is True
    assert result["minimum_reviews"] == 8  # ceil(0.8 * 10)
    assert "NOT a merchant capacity" in str(result["note"])


def test_illustrative_tiers_are_the_five_declared_values() -> None:
    assert ILLUSTRATIVE_CAPACITY_TIERS == (100, 250, 500, 1000, 2000)
