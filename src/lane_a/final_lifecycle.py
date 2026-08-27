"""Atomic one-time lifecycle record for the Lane A final evaluation.

The final evaluation may run **exactly once** per freeze commit. This module is
the only place that decides whether a run is allowed to begin, and it fails
closed in every ambiguous case.

The record lives outside the repository. It is created with ``O_EXCL`` so two
concurrent runners cannot both believe they are first, and every subsequent
transition is an atomic ``os.replace`` of a fully written temporary file in the
same directory. A partially written record can therefore never be observed.

States
------
``PREPARED``
    Every pre-access gate passed. No final-role data has been read.
``STARTED``
    Written immediately before the first final-role source access. Once this
    exists, no rerun is permitted for the freeze, ever.
``SEALED``
    Terminal success. Results are sealed and immutable.
``FAILED_AFTER_ACCESS``
    Terminal failure after access began. Not retryable, not patchable.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PREPARED = "PREPARED"
STARTED = "STARTED"
SEALED = "SEALED"
FAILED_AFTER_ACCESS = "FAILED_AFTER_ACCESS"

#: Every legal state. Anything else is a corrupt record and fails closed.
STATES: tuple[str, ...] = (PREPARED, STARTED, SEALED, FAILED_AFTER_ACCESS)

#: States from which no transition is ever legal.
TERMINAL_STATES: tuple[str, ...] = (SEALED, FAILED_AFTER_ACCESS)

#: States which prove final-role data was already accessed for this freeze.
ACCESS_BEGUN_STATES: tuple[str, ...] = (STARTED, SEALED, FAILED_AFTER_ACCESS)

#: The only legal transitions. Absence from this map is a refusal.
LEGAL_TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    PREPARED: (STARTED,),
    STARTED: (SEALED, FAILED_AFTER_ACCESS),
    SEALED: (),
    FAILED_AFTER_ACCESS: (),
}

RECORD_FILENAME = "lane_a_final_evaluation_lifecycle.json"


class LifecycleError(RuntimeError):
    """Raised when a lifecycle operation is not permitted."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    """Replace ``path`` with ``payload`` atomically, fsyncing before rename."""
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class LifecycleRecord:
    """An observed lifecycle record."""

    state: str
    run_id: str
    freeze_commit: str
    payload: Mapping[str, Any]


class FinalEvaluationLifecycle:
    """One-time lifecycle guard for a single freeze commit."""

    def __init__(self, directory: Path, *, freeze_commit: str, run_id: str) -> None:
        if not freeze_commit or len(freeze_commit) != 40:
            raise LifecycleError("freeze_commit must be a full 40-character SHA.")
        if not run_id:
            raise LifecycleError("run_id is required.")
        self.directory = Path(directory)
        self.path = self.directory / RECORD_FILENAME
        self.freeze_commit = freeze_commit
        self.run_id = run_id

    # -- reading ---------------------------------------------------------

    def read(self) -> LifecycleRecord | None:
        """Return the current record, or ``None`` when no run has begun."""
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LifecycleError(f"Lifecycle record is unreadable: {error}") from error
        if not isinstance(payload, dict):
            raise LifecycleError("Lifecycle record is not an object.")
        state = payload.get("state")
        if state not in STATES:
            raise LifecycleError(f"Lifecycle record has an unknown state: {state!r}")
        return LifecycleRecord(
            state=str(state),
            run_id=str(payload.get("run_id", "")),
            freeze_commit=str(payload.get("freeze_commit", "")),
            payload=payload,
        )

    def assert_no_prior_run(self) -> None:
        """Fail closed if any record exists for this freeze."""
        existing = self.read()
        if existing is None:
            return
        raise LifecycleError(
            "A final-evaluation lifecycle record already exists for this freeze "
            f"(state={existing.state}). The final evaluation runs exactly once "
            "and is never rerun, retried, or patched."
        )

    # -- transitions -----------------------------------------------------

    def prepare(self, payload: Mapping[str, Any]) -> LifecycleRecord:
        """Create the ``PREPARED`` record exclusively. Refuses if one exists."""
        self.directory.mkdir(parents=True, exist_ok=True)
        record = {
            **dict(payload),
            "state": PREPARED,
            "run_id": self.run_id,
            "freeze_commit": self.freeze_commit,
            "prepared_utc": _utc_now(),
            "one_run_only": True,
            "post_result_tuning_forbidden": True,
        }
        body = json.dumps(record, indent=2, sort_keys=True, default=str)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            existing = self.read()
            state = existing.state if existing else "unknown"
            raise LifecycleError(
                f"A lifecycle record already exists (state={state}); refusing to prepare."
            ) from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        return LifecycleRecord(PREPARED, self.run_id, self.freeze_commit, record)

    def _transition(self, target: str, payload: Mapping[str, Any]) -> LifecycleRecord:
        current = self.read()
        if current is None:
            raise LifecycleError(f"No lifecycle record exists; cannot move to {target}.")
        if current.run_id != self.run_id:
            raise LifecycleError(
                "Lifecycle record belongs to a different run; refusing to transition."
            )
        if current.freeze_commit != self.freeze_commit:
            raise LifecycleError(
                "Lifecycle record belongs to a different freeze; refusing to transition."
            )
        allowed = LEGAL_TRANSITIONS.get(current.state, ())
        if target not in allowed:
            raise LifecycleError(
                f"Illegal lifecycle transition {current.state} -> {target}."
            )
        record = {
            **dict(current.payload),
            **dict(payload),
            "state": target,
            f"{target.lower()}_utc": _utc_now(),
        }
        _atomic_write(self.path, record)
        return LifecycleRecord(target, self.run_id, self.freeze_commit, record)

    def start(self, payload: Mapping[str, Any] | None = None) -> LifecycleRecord:
        """Move ``PREPARED`` -> ``STARTED`` immediately before final access."""
        return self._transition(STARTED, payload or {})

    def seal(self, payload: Mapping[str, Any]) -> LifecycleRecord:
        """Move ``STARTED`` -> ``SEALED`` after results are written."""
        return self._transition(SEALED, payload)

    def fail_after_access(self, reason: str) -> LifecycleRecord:
        """Move ``STARTED`` -> ``FAILED_AFTER_ACCESS``. Never retryable."""
        return self._transition(
            FAILED_AFTER_ACCESS,
            {"failure_reason": reason, "retry_permitted": False},
        )
