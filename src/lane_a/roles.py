"""Lane A role allowlist.

``final_test`` is frozen. Nothing in this codebase may materialise it, read its
labels, score it, or count it until a separate, future task evaluates it exactly
once. The allowlist is therefore expressed positively: a role must be named in
``PERMITTED_ROLES`` to be usable, and every other role — including any future or
misspelled one — fails closed.
"""

from __future__ import annotations

from typing import Iterable

TRAINING = "training"
VALIDATION_THRESHOLD = "validation_threshold"
CALIBRATION_FIT = "calibration_fit"
CALIBRATION_EVAL = "calibration_eval"
FINAL_TEST = "final_test"

#: Roles this task may materialise, score, or read labels for.
PERMITTED_ROLES: tuple[str, ...] = (
    TRAINING,
    VALIDATION_THRESHOLD,
    CALIBRATION_FIT,
    CALIBRATION_EVAL,
)

#: Roles that are frozen and forbidden. Named explicitly so the refusal is a
#: deliberate rule rather than an accident of omission.
FROZEN_ROLES: tuple[str, ...] = (FINAL_TEST,)

#: Roles whose labels may be read, per phase, under the accepted protocol.
LABEL_READABLE_ROLES: tuple[str, ...] = (
    TRAINING,
    VALIDATION_THRESHOLD,
    CALIBRATION_FIT,
    CALIBRATION_EVAL,
)


class RoleNotPermittedError(RuntimeError):
    """Raised when a frozen or unknown role is requested."""


def assert_role_permitted(role: str) -> str:
    """Return ``role`` if it may be used; raise otherwise. Fails closed."""
    if role in FROZEN_ROLES:
        raise RoleNotPermittedError(
            f"Role {role!r} is frozen. It must not be materialised, scored, "
            "counted, or have its labels read until a separate future task "
            "evaluates it exactly once."
        )
    if role not in PERMITTED_ROLES:
        raise RoleNotPermittedError(
            f"Role {role!r} is not on the Lane A allowlist {PERMITTED_ROLES}."
        )
    return role


def assert_labels_readable(role: str) -> str:
    """Return ``role`` if its labels may be read; raise otherwise."""
    assert_role_permitted(role)
    if role not in LABEL_READABLE_ROLES:
        raise RoleNotPermittedError(f"Labels for role {role!r} may not be read.")
    return role


def filter_permitted(roles: Iterable[str]) -> tuple[str, ...]:
    """Validate every role in ``roles``, raising on the first that is not allowed."""
    return tuple(assert_role_permitted(role) for role in roles)
