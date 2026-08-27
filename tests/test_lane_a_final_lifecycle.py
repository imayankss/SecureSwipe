"""Synthetic tests for the one-time final-evaluation lifecycle.

No IEEE-CIS data, no model artifact, and no ``final_test`` row is involved.
"""

from __future__ import annotations

import json

import pytest

from src.lane_a.final_lifecycle import (
    ACCESS_BEGUN_STATES,
    FAILED_AFTER_ACCESS,
    LEGAL_TRANSITIONS,
    PREPARED,
    SEALED,
    STARTED,
    STATES,
    TERMINAL_STATES,
    FinalEvaluationLifecycle,
    LifecycleError,
)

FREEZE = "0" * 40
OTHER_FREEZE = "1" * 40


def _lifecycle(tmp_path, run_id="run-1", freeze=FREEZE):
    return FinalEvaluationLifecycle(tmp_path, freeze_commit=freeze, run_id=run_id)


def test_state_vocabulary_is_exactly_the_four_declared_states():
    assert STATES == (PREPARED, STARTED, SEALED, FAILED_AFTER_ACCESS)
    assert TERMINAL_STATES == (SEALED, FAILED_AFTER_ACCESS)
    assert ACCESS_BEGUN_STATES == (STARTED, SEALED, FAILED_AFTER_ACCESS)


def test_terminal_states_have_no_outgoing_transition():
    for state in TERMINAL_STATES:
        assert LEGAL_TRANSITIONS[state] == ()


def test_freeze_commit_must_be_a_full_sha(tmp_path):
    with pytest.raises(LifecycleError):
        FinalEvaluationLifecycle(tmp_path, freeze_commit="abc", run_id="r")


def test_run_id_is_required(tmp_path):
    with pytest.raises(LifecycleError):
        FinalEvaluationLifecycle(tmp_path, freeze_commit=FREEZE, run_id="")


def test_happy_path_prepared_started_sealed(tmp_path):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.assert_no_prior_run()
    assert lifecycle.prepare({"preflight": "ok"}).state == PREPARED
    assert lifecycle.start().state == STARTED
    assert lifecycle.seal({"result": "x"}).state == SEALED
    assert lifecycle.read().state == SEALED


def test_failure_path_is_terminal_and_records_no_retry(tmp_path):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.prepare({})
    lifecycle.start()
    record = lifecycle.fail_after_access("boom")
    assert record.state == FAILED_AFTER_ACCESS
    assert record.payload["retry_permitted"] is False
    assert "boom" in record.payload["failure_reason"]


def test_prepare_twice_is_refused(tmp_path):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.prepare({})
    with pytest.raises(LifecycleError, match="already exists"):
        lifecycle.prepare({})


@pytest.mark.parametrize("state", [PREPARED, STARTED, SEALED, FAILED_AFTER_ACCESS])
def test_a_second_run_is_refused_from_every_existing_state(tmp_path, state):
    first = _lifecycle(tmp_path, run_id="first")
    first.prepare({})
    if state in (STARTED, SEALED, FAILED_AFTER_ACCESS):
        first.start()
    if state == SEALED:
        first.seal({})
    if state == FAILED_AFTER_ACCESS:
        first.fail_after_access("earlier failure")

    second = _lifecycle(tmp_path, run_id="second")
    with pytest.raises(LifecycleError, match="exactly once"):
        second.assert_no_prior_run()


def test_start_without_prepare_is_refused(tmp_path):
    with pytest.raises(LifecycleError, match="No lifecycle record"):
        _lifecycle(tmp_path).start()


def test_seal_without_start_is_refused(tmp_path):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.prepare({})
    with pytest.raises(LifecycleError, match="Illegal lifecycle transition"):
        lifecycle.seal({})


@pytest.mark.parametrize("terminal", [SEALED, FAILED_AFTER_ACCESS])
def test_terminal_states_refuse_further_transitions(tmp_path, terminal):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.prepare({})
    lifecycle.start()
    if terminal == SEALED:
        lifecycle.seal({})
    else:
        lifecycle.fail_after_access("x")
    with pytest.raises(LifecycleError, match="Illegal lifecycle transition"):
        lifecycle.seal({})
    with pytest.raises(LifecycleError, match="Illegal lifecycle transition"):
        lifecycle.start()


def test_transition_refuses_a_record_from_another_run(tmp_path):
    _lifecycle(tmp_path, run_id="first").prepare({})
    with pytest.raises(LifecycleError, match="different run"):
        _lifecycle(tmp_path, run_id="second").start()


def test_transition_refuses_a_record_from_another_freeze(tmp_path):
    _lifecycle(tmp_path, run_id="r").prepare({})
    other = FinalEvaluationLifecycle(tmp_path, freeze_commit=OTHER_FREEZE, run_id="r")
    with pytest.raises(LifecycleError, match="different freeze"):
        other.start()


def test_corrupt_record_fails_closed(tmp_path):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.prepare({})
    lifecycle.path.write_text("{not json", encoding="utf-8")
    with pytest.raises(LifecycleError, match="unreadable"):
        lifecycle.read()


def test_unknown_state_fails_closed(tmp_path):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.prepare({})
    lifecycle.path.write_text(json.dumps({"state": "WHATEVER"}), encoding="utf-8")
    with pytest.raises(LifecycleError, match="unknown state"):
        lifecycle.read()


def test_prepared_record_declares_one_run_only(tmp_path):
    record = _lifecycle(tmp_path).prepare({})
    assert record.payload["one_run_only"] is True
    assert record.payload["post_result_tuning_forbidden"] is True


def test_record_is_written_outside_any_repository_path(tmp_path):
    lifecycle = _lifecycle(tmp_path)
    lifecycle.prepare({})
    assert lifecycle.path.is_relative_to(tmp_path)
