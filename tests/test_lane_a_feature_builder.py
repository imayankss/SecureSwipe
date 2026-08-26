"""Synthetic-only tests for the locked Lane A serving core and feature builder.

Nothing here reads the IEEE-CIS CSVs, the private role assignment, any label, or
any real row. Every fixture is constructed in-process.
"""

from __future__ import annotations

import pytest

from src.lane_a.feature_builder import (
    ESCAPE_PREFIX,
    RESERVED_MISSING,
    BuilderPolicy,
    FeatureBuildError,
    ReservedTokenCollision,
    assert_selection_is_locked,
    build_row,
    row_digest,
)
from src.lane_a.serving_schema import (
    FORBIDDEN_EXACT,
    IDENTITY_PRESENCE_FEATURE,
    SCHEMA_FIELD_NAMES,
    SOURCE_FIELD_NAMES,
    SchemaLockError,
    assert_no_lane_b_names,
    assert_schema_locked,
    is_forbidden,
    validate_against_contract,
)


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "TransactionAmt": "68.50",
        "ProductCD": "W",
        "card1": "1001",
        "card2": "321.0",
        "card3": "150.0",
        "card4": "brand_a",
        "card5": "226.0",
        "card6": "debit",
        "addr1": "204.0",
        "addr2": "87.0",
        "P_emaildomain": "example.test",
        "DeviceType": "desktop",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- 1. exactly 13


def test_schema_lock_holds_and_cross_checks_the_contract() -> None:
    assert_schema_locked()
    summary = validate_against_contract()
    assert summary["model_inputs"] == 13
    assert summary["source_fields"] == 12
    assert summary["derived_fields"] == 1
    assert len(SCHEMA_FIELD_NAMES) == 13


def test_builder_emits_exactly_the_thirteen_locked_features_in_order() -> None:
    built = build_row(_row(), identity_record_present=True, device_type="desktop")
    assert tuple(built) == SCHEMA_FIELD_NAMES
    assert len(built) == 13
    assert set(built) == {
        "TransactionAmt", "ProductCD", "card1", "card2", "card3", "card4",
        "card5", "card6", "addr1", "addr2", "P_emaildomain", "DeviceType",
        IDENTITY_PRESENCE_FEATURE,
    }


def test_selection_must_be_exactly_the_locked_schema() -> None:
    assert_selection_is_locked(SCHEMA_FIELD_NAMES)
    with pytest.raises(SchemaLockError):
        assert_selection_is_locked(SCHEMA_FIELD_NAMES[:-1])  # too few
    with pytest.raises(SchemaLockError):
        assert_selection_is_locked(tuple(reversed(SCHEMA_FIELD_NAMES)))  # wrong order


# ------------------------------------------------- 2. every forbidden field dies


@pytest.mark.parametrize("name", sorted(FORBIDDEN_EXACT))
def test_named_forbidden_columns_are_rejected(name: str) -> None:
    assert is_forbidden(name)
    with pytest.raises(FeatureBuildError):
        assert_selection_is_locked([*SCHEMA_FIELD_NAMES, name])


@pytest.mark.parametrize(
    "name",
    ["M1", "M9", "C1", "C14", "D1", "D15", "V1", "V28", "V339", "dist1", "dist2",
     "id_01", "id_38", "DeviceInfo", "R_emaildomain"],
)
def test_forbidden_families_are_rejected(name: str) -> None:
    assert is_forbidden(name)
    with pytest.raises(FeatureBuildError):
        assert_selection_is_locked([*SCHEMA_FIELD_NAMES, name])


def test_no_locked_field_is_itself_forbidden() -> None:
    for name in SCHEMA_FIELD_NAMES:
        assert not is_forbidden(name)


# --------------------------------------------- 3. Lane B names cannot enter


def test_lane_b_names_cannot_enter_the_serving_core() -> None:
    from src.preprocessing.feature_config import ALL_FEATURES

    assert_no_lane_b_names(ALL_FEATURES)  # no overlap today
    for lane_b_name in ("Time", "Amount", "V1", "V28"):
        assert lane_b_name not in SCHEMA_FIELD_NAMES


def test_injecting_a_lane_b_name_into_the_core_is_detected() -> None:
    with pytest.raises(SchemaLockError):
        assert_no_lane_b_names(["ProductCD"])  # pretend Lane B declared this name


def test_lane_b_v_names_are_forbidden_by_prefix() -> None:
    for name in ("V1", "V14", "V28"):
        assert is_forbidden(name)


# ------------------------- 4. missing DeviceType -> reserved token + false flag


def test_absent_identity_yields_reserved_token_and_false_flag() -> None:
    built = build_row(_row(), identity_record_present=False, device_type=None)
    assert built["DeviceType"] == RESERVED_MISSING
    assert built[IDENTITY_PRESENCE_FEATURE] is False


def test_device_type_ignored_when_identity_absent() -> None:
    """A stray device value must not resurrect a non-existent identity record."""
    built = build_row(_row(), identity_record_present=False, device_type="mobile")
    assert built["DeviceType"] == RESERVED_MISSING
    assert built[IDENTITY_PRESENCE_FEATURE] is False


def test_identity_present_but_device_missing_keeps_flag_true() -> None:
    built = build_row(_row(), identity_record_present=True, device_type="")
    assert built["DeviceType"] == RESERVED_MISSING
    assert built[IDENTITY_PRESENCE_FEATURE] is True


@pytest.mark.parametrize("token", ["", "  ", "NaN", "NA", "null", "None"])
def test_missing_categoricals_use_the_one_reserved_token(token: str) -> None:
    built = build_row(_row(ProductCD=token), identity_record_present=True, device_type="desktop")
    assert built["ProductCD"] == RESERVED_MISSING


def test_missing_numerics_stay_null_and_are_never_imputed() -> None:
    built = build_row(_row(addr1="", card2="NaN"), identity_record_present=True, device_type="d")
    assert built["addr1"] is None
    assert built["card2"] is None


def test_identity_flag_must_be_a_real_bool() -> None:
    with pytest.raises(FeatureBuildError):
        build_row(_row(), identity_record_present=1, device_type="d")  # type: ignore[arg-type]


# ------------------------------- 5. a real value equal to the reserved token


def test_real_value_equal_to_reserved_token_is_rejected_by_default() -> None:
    with pytest.raises(ReservedTokenCollision):
        build_row(
            _row(ProductCD=RESERVED_MISSING), identity_record_present=True, device_type="d"
        )


def test_reserved_token_collision_can_be_escaped_when_policy_allows() -> None:
    built = build_row(
        _row(P_emaildomain=RESERVED_MISSING),
        identity_record_present=True,
        device_type="d",
        policy=BuilderPolicy(on_reserved_collision="escape"),
    )
    assert built["P_emaildomain"] == f"{ESCAPE_PREFIX}{RESERVED_MISSING}"
    assert built["P_emaildomain"] != RESERVED_MISSING


def test_escape_prefix_in_real_data_is_also_rejected() -> None:
    with pytest.raises(ReservedTokenCollision):
        build_row(
            _row(card4=f"{ESCAPE_PREFIX}spoof"), identity_record_present=True, device_type="d"
        )


def test_unknown_collision_policy_is_refused() -> None:
    with pytest.raises(FeatureBuildError):
        BuilderPolicy(on_reserved_collision="ignore")


# --------------------------------------------------------- 6. determinism


def test_repeated_builds_are_identical() -> None:
    first = build_row(_row(), identity_record_present=True, device_type="desktop")
    second = build_row(_row(), identity_record_present=True, device_type="desktop")
    assert first == second
    assert row_digest([first]) == row_digest([second])


def test_digest_changes_when_any_field_changes() -> None:
    base = build_row(_row(), identity_record_present=True, device_type="desktop")
    changed = build_row(_row(card3="151.0"), identity_record_present=True, device_type="desktop")
    assert row_digest([base]) != row_digest([changed])


def test_digest_distinguishes_missing_from_present() -> None:
    present = build_row(_row(), identity_record_present=True, device_type="desktop")
    absent = build_row(_row(), identity_record_present=False, device_type=None)
    assert row_digest([present]) != row_digest([absent])


def test_digest_is_order_sensitive_so_output_ordering_is_part_of_the_freeze() -> None:
    a = build_row(_row(card1="1"), identity_record_present=True, device_type="d")
    b = build_row(_row(card1="2"), identity_record_present=True, device_type="d")
    assert row_digest([a, b]) != row_digest([b, a])


# ------------------------------------------ 7. labels never accepted or read


@pytest.mark.parametrize("label", ["isFraud", "label", "target", "y"])
def test_label_in_the_source_row_is_refused(label: str) -> None:
    with pytest.raises(FeatureBuildError):
        build_row(_row(**{label: "1"}), identity_record_present=True, device_type="d")


@pytest.mark.parametrize("label", ["isFraud", "label", "target", "y"])
def test_label_cannot_be_selected_as_an_input(label: str) -> None:
    with pytest.raises(FeatureBuildError):
        assert_selection_is_locked([*SCHEMA_FIELD_NAMES, label])


def test_builder_signature_exposes_no_label_parameter() -> None:
    import inspect

    parameters = " ".join(inspect.signature(build_row).parameters).lower()
    assert "label" not in parameters and "fraud" not in parameters and "target" not in parameters


def test_builder_module_performs_no_fitting_or_aggregation() -> None:
    import inspect

    from src.lane_a import feature_builder

    source = inspect.getsource(feature_builder)
    for banned in (".fit(", "groupby", "rolling(", "expanding(", "target_encod", "cumsum"):
        assert banned not in source


# --------------------------------------------------------- validation rules


def test_transaction_amount_must_be_finite_and_non_negative() -> None:
    for bad in ("-0.01", "inf", "-inf", "nan_value"):
        with pytest.raises(FeatureBuildError):
            build_row(_row(TransactionAmt=bad), identity_record_present=True, device_type="d")


def test_zero_amount_is_permitted() -> None:
    built = build_row(_row(TransactionAmt="0"), identity_record_present=True, device_type="d")
    assert built["TransactionAmt"] == 0.0


def test_missing_required_source_column_is_refused() -> None:
    incomplete = _row()
    del incomplete["card5"]
    with pytest.raises(FeatureBuildError):
        build_row(incomplete, identity_record_present=True, device_type="d")


def test_non_numeric_in_a_numeric_column_is_refused() -> None:
    with pytest.raises(FeatureBuildError):
        build_row(_row(card1="not_a_number"), identity_record_present=True, device_type="d")


def test_source_field_count_is_twelve() -> None:
    assert len(SOURCE_FIELD_NAMES) == 12


def test_transaction_side_device_type_is_ignored_in_favour_of_the_identity_join() -> None:
    """A DeviceType key on the transaction row must not bypass the identity join."""
    built = build_row(
        _row(DeviceType="spoofed_from_transaction_row"),
        identity_record_present=True,
        device_type="from_identity_join",
    )
    assert built["DeviceType"] == "from_identity_join"

    absent = build_row(
        _row(DeviceType="spoofed_from_transaction_row"),
        identity_record_present=False,
        device_type=None,
    )
    assert absent["DeviceType"] == RESERVED_MISSING


def test_transaction_row_need_not_carry_device_type() -> None:
    row_without_device = _row()
    del row_without_device["DeviceType"]
    built = build_row(row_without_device, identity_record_present=True, device_type="desktop")
    assert built["DeviceType"] == "desktop"
    assert tuple(built) == SCHEMA_FIELD_NAMES
