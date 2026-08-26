"""Synthetic-only tests for the Lane A role allowlist."""

from __future__ import annotations

import pytest

from src.lane_a.roles import (
    FINAL_TEST,
    FROZEN_ROLES,
    LABEL_READABLE_ROLES,
    PERMITTED_ROLES,
    RoleNotPermittedError,
    assert_labels_readable,
    assert_role_permitted,
    filter_permitted,
)


def test_permitted_roles_are_exactly_the_four_development_roles() -> None:
    assert PERMITTED_ROLES == (
        "training",
        "validation_threshold",
        "calibration_fit",
        "calibration_eval",
    )
    assert FINAL_TEST not in PERMITTED_ROLES


def test_final_test_is_frozen_and_rejected() -> None:
    assert FROZEN_ROLES == (FINAL_TEST,)
    with pytest.raises(RoleNotPermittedError, match="frozen"):
        assert_role_permitted(FINAL_TEST)


def test_final_test_labels_are_rejected() -> None:
    with pytest.raises(RoleNotPermittedError):
        assert_labels_readable(FINAL_TEST)
    assert FINAL_TEST not in LABEL_READABLE_ROLES


@pytest.mark.parametrize(
    "role", ["", "Final_Test", "final test", "test", "holdout", "FINAL_TEST", "unknown"]
)
def test_unknown_or_misspelled_roles_fail_closed(role: str) -> None:
    with pytest.raises(RoleNotPermittedError):
        assert_role_permitted(role)


@pytest.mark.parametrize("role", PERMITTED_ROLES)
def test_permitted_roles_pass(role: str) -> None:
    assert assert_role_permitted(role) == role
    assert assert_labels_readable(role) == role


def test_filter_permitted_raises_on_the_first_forbidden_role() -> None:
    assert filter_permitted(PERMITTED_ROLES) == PERMITTED_ROLES
    with pytest.raises(RoleNotPermittedError):
        filter_permitted(["training", FINAL_TEST])
