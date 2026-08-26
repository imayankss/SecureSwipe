"""Synthetic-only tests for the Lane A feature contract and profiling.

Nothing here reads the IEEE-CIS CSVs, the private role assignment, any label,
or any real row. Every fixture is constructed in-process.
"""

from __future__ import annotations

import pytest

from src.lane_a.feature_contract import (
    JOIN_KEY,
    LABEL_COLUMN,
    NAMESPACE,
    PARTITION_KEY,
    RULES_BY_NAME,
    Eligibility,
    FeatureContractError,
    assert_disjoint_from,
    benchmark_only_features,
    candidate_snapshot_features,
    contract_summary,
    optional_features,
    prohibited_features,
    qualified,
    serving_eligible_features,
    validate_selection,
)
from src.lane_a.profiling import (
    CARDINALITY_CAP,
    ColumnAccumulator,
    ProfilingError,
    new_accumulators,
    profile_is_publishable,
)

# --------------------------------------------------------------------------
# 1. No ULB / IEEE namespace mixing
# --------------------------------------------------------------------------


def test_raw_names_collide_with_ulb_proving_the_hazard_is_real() -> None:
    from src.preprocessing.feature_config import ALL_FEATURES

    raw_overlap = set(RULES_BY_NAME) & set(ALL_FEATURES)
    assert raw_overlap, "expected raw V-name collision; the qualifier exists to defuse it"
    assert {"V1", "V28"} <= raw_overlap


def test_qualified_lane_a_names_are_disjoint_from_ulb() -> None:
    from src.preprocessing.feature_config import ALL_FEATURES

    assert_disjoint_from(ALL_FEATURES)
    assert all(name.startswith(f"{NAMESPACE}::") for name in qualified(("V1", "TransactionAmt")))


def test_contract_module_does_not_import_lane_b() -> None:
    import inspect

    from src.lane_a import feature_contract

    source = inspect.getsource(feature_contract)
    assert "feature_config" not in source
    assert "preprocessing" not in source


def test_qualifying_an_unknown_column_is_refused() -> None:
    with pytest.raises(FeatureContractError):
        qualified(("Amount",))  # a Lane B name, not a Lane A column


# --------------------------------------------------------------------------
# 2. No label field accepted as a model feature
# --------------------------------------------------------------------------


def test_label_is_prohibited_everywhere() -> None:
    assert RULES_BY_NAME[LABEL_COLUMN].eligibility is Eligibility.PROHIBITED
    assert LABEL_COLUMN not in candidate_snapshot_features()
    assert LABEL_COLUMN not in benchmark_only_features()
    assert LABEL_COLUMN not in serving_eligible_features()


@pytest.mark.parametrize("for_serving", [True, False])
def test_selecting_the_label_raises(for_serving: bool) -> None:
    with pytest.raises(FeatureContractError):
        validate_selection(["TransactionAmt", LABEL_COLUMN], for_serving=for_serving)


@pytest.mark.parametrize("name", [JOIN_KEY, PARTITION_KEY])
def test_identifier_and_partition_key_are_prohibited(name: str) -> None:
    assert name in prohibited_features()
    with pytest.raises(FeatureContractError):
        validate_selection([name], for_serving=False)


def test_profiling_refuses_the_label_column() -> None:
    with pytest.raises(ProfilingError):
        new_accumulators(("TransactionAmt", LABEL_COLUMN))


# --------------------------------------------------------------------------
# 3. No unsafe C*, D* or V* reaches the serving-candidate set
# --------------------------------------------------------------------------


def test_no_c_d_or_v_column_is_serving_eligible() -> None:
    serving = set(serving_eligible_features())
    offenders = [
        name
        for name in serving
        if name.startswith(("C", "D", "V"))
        and name not in {"DeviceType", "DeviceInfo"}
    ]
    assert offenders == []


def test_every_c_d_v_column_is_benchmark_only_and_needs_proof() -> None:
    families = {"count_aggregate", "timedelta", "vesta_engineered"}
    covered = [rule for rule in RULES_BY_NAME.values() if rule.family in families]
    assert len(covered) == 14 + 15 + 339
    for rule in covered:
        assert rule.eligibility is Eligibility.BENCHMARK_ONLY
        assert rule.requires_point_in_time_proof


@pytest.mark.parametrize("name", ["C1", "C14", "D1", "D15", "V1", "V339", "dist1"])
def test_serving_selection_of_unproven_columns_raises(name: str) -> None:
    with pytest.raises(FeatureContractError):
        validate_selection([name], for_serving=True)
    # benchmark use remains permitted
    assert validate_selection([name], for_serving=False) == (name,)


def test_serving_whitelist_is_exactly_the_proof_free_candidates() -> None:
    for name in serving_eligible_features():
        rule = RULES_BY_NAME[name]
        assert rule.eligibility is Eligibility.CANDIDATE_SNAPSHOT
        assert not rule.requires_point_in_time_proof


def test_duplicate_selection_is_refused() -> None:
    with pytest.raises(FeatureContractError):
        validate_selection(["card1", "card1"], for_serving=True)


# --------------------------------------------------------------------------
# 4. Identity missingness is preserved as an explicit signal
# --------------------------------------------------------------------------


def test_identity_and_device_columns_are_marked_optional() -> None:
    optional = set(optional_features())
    assert {"DeviceType", "DeviceInfo", "id_01", "id_38"} <= optional
    assert LABEL_COLUMN not in optional


def test_absent_identity_is_counted_as_missing_not_dropped() -> None:
    accumulator = ColumnAccumulator(name="id_01")
    for _ in range(24):
        accumulator.update("5")
    for _ in range(76):  # transactions with no identity record at all
        accumulator.update("")
    profile = accumulator.finalize()
    assert profile["rows_seen"] == 100
    assert profile["present_count"] == 24
    assert profile["missing_count"] == 76
    assert profile["missing_rate"] == pytest.approx(0.76)


def test_missing_tokens_are_not_imputed_to_a_value() -> None:
    accumulator = ColumnAccumulator(name="DeviceInfo")
    for token in ("", "  ", "NaN", "NA", "null", "None"):
        accumulator.update(token)
    profile = accumulator.finalize()
    assert profile["present_count"] == 0
    assert profile["missing_count"] == 6
    assert profile["cardinality"] == 0


# --------------------------------------------------------------------------
# Profiling output safety and correctness
# --------------------------------------------------------------------------


def test_profile_contains_counts_only_and_never_a_value() -> None:
    accumulator = ColumnAccumulator(name="P_emaildomain")
    for value in ("alpha.example", "beta.example", "alpha.example"):
        accumulator.update(value)
    profile = accumulator.finalize()
    assert profile_is_publishable(profile)
    assert profile["cardinality"] == 2
    rendered = repr(profile)
    assert "alpha.example" not in rendered and "beta.example" not in rendered


def test_nan_token_counts_as_missing_but_infinity_counts_as_invalid() -> None:
    """These are different failures and must not be conflated.

    A bare ``nan`` in a CSV is how exporters spell "absent", so it is missing
    data. ``inf`` is a value that was actually written and is not finite, so it
    is an invalid value. Collapsing the two would hide real corruption inside a
    missingness rate.
    """
    accumulator = ColumnAccumulator(name="TransactionAmt", non_negative_expected=True)
    for value in ("10.5", "-3", "nan", "inf", "2"):
        accumulator.update(value)
    profile = accumulator.finalize()
    assert profile["missing_count"] == 1  # the "nan" token
    assert profile["invalid_non_finite_count"] == 1  # the "inf" value
    assert profile["invalid_negative_count"] == 1
    assert "negative_values_where_non_negative_expected" in profile["invalid_value_violations"]
    assert "non_finite_values_present" in profile["invalid_value_violations"]


def test_mixed_types_are_reported_not_coerced() -> None:
    accumulator = ColumnAccumulator(name="id_30")
    accumulator.update("7")
    accumulator.update("some_text")
    profile = accumulator.finalize()
    assert profile["dtype_inferred"] == "mixed"
    assert "mixed_types_observed" in profile["invalid_value_violations"]


def test_cardinality_caps_instead_of_growing_unbounded() -> None:
    accumulator = ColumnAccumulator(name="V1")
    for index in range(CARDINALITY_CAP + 50):
        accumulator.update(str(index))
    profile = accumulator.finalize()
    assert profile["cardinality_capped"] is True
    assert profile["cardinality"] == f">={CARDINALITY_CAP}"


def test_contract_summary_totals_reconcile() -> None:
    summary = contract_summary()
    assert summary["total_columns"] == 434  # 394 transaction + 41 identity - shared key
    assert (
        summary["candidate_snapshot"] + summary["benchmark_only"] + summary["prohibited"]
        == summary["total_columns"]
    )
    assert summary["serving_eligible"] <= summary["candidate_snapshot"]
