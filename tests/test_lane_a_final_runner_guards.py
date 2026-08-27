"""Synthetic guard and rehearsal tests for the one-time final-evaluation runner.

Every source, artifact and manifest here is generated in-process. No IEEE-CIS
file is opened, no real model is loaded, and no ``final_test`` row of the real
partition is read. The rehearsal drives the complete runner path end to end on
synthetic data so the ordering guarantees are proven rather than asserted.
"""

from __future__ import annotations

import builtins
import csv
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pytest

import scripts.lane_a_run_final_evaluation as runner
from src.lane_a.final_lifecycle import (
    PREPARED,
    SEALED,
    STARTED,
    FinalEvaluationLifecycle,
    LifecycleError,
)
from src.lane_a.partition import assignment_digest
from src.lane_a.serving_schema import IDENTITY_PRESENCE_FEATURE, NUMERIC_FIELDS
from src.lane_a.variants import SUPERSET_FIELDS

FREEZE = "a" * 40
ROWS = 400


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -- synthetic world -----------------------------------------------------


class _StubPipeline:
    """Deterministic stand-in for the frozen pipeline."""

    def predict_proba(self, frame):
        amount = np.asarray(frame["TransactionAmt"], dtype=float)
        positive = 1.0 / (1.0 + np.exp(-(amount - 100.0) / 40.0))
        return np.column_stack([1.0 - positive, positive])


class _StubCalibrator:
    """Deterministic stand-in for the frozen Platt calibrator."""

    def predict_proba(self, values):
        flat = np.asarray(values, dtype=float).reshape(-1)
        calibrated = np.clip(flat * 0.9 + 0.005, 0.0, 1.0)
        return np.column_stack([1.0 - calibrated, calibrated])


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Build synthetic sources, artifacts and a matching authorization manifest."""
    rng = np.random.default_rng(19)
    private = tmp_path / "private"
    private.mkdir()

    transaction_fields = [
        name
        for name in SUPERSET_FIELDS
        if name not in ("DeviceType", "DeviceInfo") and name != IDENTITY_PRESENCE_FEATURE
    ]
    transactions = tmp_path / "transactions.csv"
    identity = tmp_path / "identity.csv"
    assignment = tmp_path / "assignment.csv"

    with transactions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TransactionID", "TransactionDT", "isFraud", *transaction_fields])
        for index in range(ROWS):
            amount = float(rng.uniform(5.0, 400.0))
            label = int(rng.random() < (0.03 + 0.25 * (amount > 300)))
            values = []
            for name in transaction_fields:
                if name == "TransactionAmt":
                    values.append(f"{amount:.2f}")
                elif name in NUMERIC_FIELDS:
                    values.append(str(int(rng.integers(1, 500))))
                else:
                    values.append(f"c{int(rng.integers(0, 4))}")
            writer.writerow([index + 1, 86_400 * index // 8, label, *values])

    with identity.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TransactionID", "DeviceType", "DeviceInfo"])
        for index in range(0, ROWS, 2):  # half the rows have an identity record
            writer.writerow([index + 1, "mobile", "generic"])

    assignment_pairs = [
        (index + 1, "final_test" if index % 2 == 0 else "training") for index in range(ROWS)
    ]
    with assignment.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["TransactionID", "role"])
        writer.writerows(assignment_pairs)

    pipeline_path = tmp_path / "pipeline.joblib"
    calibrator_path = tmp_path / "calibrator.joblib"
    pipeline_path.write_bytes(b"synthetic-pipeline")
    calibrator_path.write_bytes(b"synthetic-calibrator")

    frozen = {
        "selected_schema_digest": "s" * 64,
        "preprocessing_digest": "p" * 64,
        "xgboost_configuration_digest": "x" * 64,
        "pipeline_sha256": _sha(pipeline_path),
        "calibrator_sha256": _sha(calibrator_path),
        "calibration_decision_digest": "d" * 64,
        "capacity_policy_digest": "c" * 64,
        "capacity_frontier_digest": "f" * 64,
    }
    source_digests = {
        "transactions": _sha(transactions),
        "identity": _sha(identity),
        "role_assignment_digest": assignment_digest(assignment_pairs),
    }

    monkeypatch.setattr(runner, "FROZEN_DIGESTS", frozen)
    monkeypatch.setattr(runner, "FROZEN_SOURCE_DIGESTS", source_digests)
    monkeypatch.setattr(runner, "verify_repository_state", lambda sha: None)
    monkeypatch.setattr(
        joblib,
        "load",
        lambda path: _StubPipeline() if "pipeline" in str(path) else _StubCalibrator(),
    )

    manifest = {
        "schema_version": runner.MANIFEST_SCHEMA_VERSION,
        "freeze_commit": FREEZE,
        "final_role": "final_test",
        "selected_variant": "E",
        "protocol_sha256": runner.sha256_file(runner.PROTOCOL_DOCUMENT),
        "boundary_amendment_sha256": runner.sha256_file(runner.BOUNDARY_AMENDMENT_DOCUMENT),
        "runner_sha256": runner.sha256_file(
            runner.PROJECT_ROOT / "scripts" / "lane_a_run_final_evaluation.py"
        ),
        "module_sha256": {
            name: runner.sha256_file(runner.PROJECT_ROOT / relative)
            for name, relative in (
                ("final_evaluation", "src/lane_a/final_evaluation.py"),
                ("final_lifecycle", "src/lane_a/final_lifecycle.py"),
                ("capacity", "src/lane_a/capacity.py"),
                ("variants", "src/lane_a/variants.py"),
            )
        },
        "frozen": frozen,
        "role_assignment_digest": source_digests["role_assignment_digest"],
        "sources": {
            "transactions": {"path": str(transactions), "sha256": source_digests["transactions"]},
            "identity": {"path": str(identity), "sha256": source_digests["identity"]},
            "role_assignment": {
                "path": str(assignment),
                "assignment_digest": source_digests["role_assignment_digest"],
            },
        },
        "artifacts": {
            "pipeline": {"path": str(pipeline_path)},
            "calibrator": {"path": str(calibrator_path)},
        },
        "environment": runner.environment_fingerprint(),
        "one_run_only": True,
        "post_result_tuning_forbidden": True,
    }
    return {
        "tmp": tmp_path,
        "private": private,
        "manifest": manifest,
        "manifest_path": tmp_path / "authorization.json",
        "transactions": transactions,
        "assignment": assignment,
    }


def _write_manifest(world, override=None):
    payload = json.loads(json.dumps(world["manifest"]))
    if override:
        override(payload)
    body = json.dumps(payload, indent=2, sort_keys=True)
    world["manifest_path"].write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode()).hexdigest()


def _argv(world, digest, **extra):
    args = [
        "--execute-final-test",
        "--expected-freeze-sha",
        FREEZE,
        "--authorization-manifest",
        str(world["manifest_path"]),
        "--expected-manifest-sha256",
        digest,
        "--private-output-dir",
        str(world["private"]),
    ]
    for key, value in extra.items():
        args.extend([f"--{key.replace('_', '-')}", str(value)])
    return args


# -- argument and flag refusals ------------------------------------------


def test_missing_execute_final_test_flag_is_refused(world):
    digest = _write_manifest(world)
    argv = [token for token in _argv(world, digest) if token != "--execute-final-test"]
    with pytest.raises(runner.FinalRunnerError, match="--execute-final-test is required"):
        runner.main(argv)


@pytest.mark.parametrize(
    "flag",
    ["--force", "--retry", "--rerun", "--skip", "--no-verify", "--fallback", "--variant", "--tier"],
)
def test_override_flags_are_refused(world, flag):
    digest = _write_manifest(world)
    with pytest.raises(runner.FinalRunnerError, match="no override, retry"):
        runner.main([*_argv(world, digest), flag])


def test_short_freeze_sha_is_refused(world):
    digest = _write_manifest(world)
    argv = _argv(world, digest)
    argv[argv.index(FREEZE)] = "abc123"
    with pytest.raises(runner.FinalRunnerError, match="40-character"):
        runner.main(argv)


def test_private_output_inside_the_repository_is_refused(world):
    digest = _write_manifest(world)
    argv = _argv(world, digest)
    argv[argv.index(str(world["private"]))] = str(runner.PROJECT_ROOT / "docs")
    with pytest.raises(runner.FinalRunnerError, match="outside the repository"):
        runner.main(argv)


# -- manifest refusals ---------------------------------------------------


def test_absent_manifest_is_refused(world):
    digest = _write_manifest(world)
    world["manifest_path"].unlink()
    with pytest.raises(runner.FinalRunnerError, match="manifest not found"):
        runner.main(_argv(world, digest))


def test_malformed_manifest_is_refused(world):
    _write_manifest(world)
    world["manifest_path"].write_text("{not json", encoding="utf-8")
    digest = hashlib.sha256(world["manifest_path"].read_bytes()).hexdigest()
    with pytest.raises(runner.FinalRunnerError, match="malformed"):
        runner.main(_argv(world, digest))


def test_manifest_digest_mismatch_is_refused(world):
    _write_manifest(world)
    with pytest.raises(runner.FinalRunnerError, match="manifest digest does not match"):
        runner.main(_argv(world, "0" * 64))


def test_manifest_bound_to_another_freeze_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(freeze_commit="b" * 40))
    with pytest.raises(runner.FinalRunnerError, match="different freeze commit"):
        runner.main(_argv(world, digest))


def test_manifest_without_one_run_only_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(one_run_only=False))
    with pytest.raises(runner.FinalRunnerError, match="one-run-only"):
        runner.main(_argv(world, digest))


def test_manifest_permitting_post_result_tuning_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(post_result_tuning_forbidden=False))
    with pytest.raises(runner.FinalRunnerError, match="post-result tuning"):
        runner.main(_argv(world, digest))


def test_manifest_authorising_another_role_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(final_role="training"))
    with pytest.raises(runner.FinalRunnerError, match="does not authorise the final role"):
        runner.main(_argv(world, digest))


def test_unsupported_schema_version_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(schema_version="something-else"))
    with pytest.raises(runner.FinalRunnerError, match="schema version"):
        runner.main(_argv(world, digest))


def test_missing_required_key_is_refused(world):
    digest = _write_manifest(world, lambda m: m.pop("frozen"))
    with pytest.raises(runner.FinalRunnerError, match="missing 'frozen'"):
        runner.main(_argv(world, digest))


# -- digest refusals -----------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "selected_schema_digest",
        "preprocessing_digest",
        "xgboost_configuration_digest",
        "pipeline_sha256",
        "calibrator_sha256",
        "calibration_decision_digest",
        "capacity_policy_digest",
        "capacity_frontier_digest",
    ],
)
def test_frozen_digest_mismatch_is_refused(world, key):
    digest = _write_manifest(world, lambda m: m["frozen"].update({key: "9" * 64}))
    with pytest.raises(runner.FinalRunnerError, match=f"Frozen digest mismatch for {key}"):
        runner.main(_argv(world, digest))


def test_protocol_digest_mismatch_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(protocol_sha256="9" * 64))
    with pytest.raises(runner.FinalRunnerError, match="protocol digest"):
        runner.main(_argv(world, digest))


def test_runner_digest_mismatch_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(runner_sha256="9" * 64))
    with pytest.raises(runner.FinalRunnerError, match="Runner code digest"):
        runner.main(_argv(world, digest))


@pytest.mark.parametrize("module", ["final_evaluation", "final_lifecycle", "capacity", "variants"])
def test_module_digest_mismatch_is_refused(world, module):
    digest = _write_manifest(world, lambda m: m["module_sha256"].update({module: "9" * 64}))
    with pytest.raises(runner.FinalRunnerError, match=f"Module digest mismatch for {module}"):
        runner.main(_argv(world, digest))


@pytest.mark.parametrize("source", ["transactions", "identity"])
def test_declared_source_digest_mismatch_is_refused(world, source):
    digest = _write_manifest(world, lambda m: m["sources"][source].update({"sha256": "9" * 64}))
    with pytest.raises(runner.FinalRunnerError, match="not the frozen IEEE-CIS artifact"):
        runner.main(_argv(world, digest))


def test_declared_assignment_digest_mismatch_is_refused(world):
    digest = _write_manifest(
        world,
        lambda m: m["sources"]["role_assignment"].update({"assignment_digest": "9" * 64}),
    )
    with pytest.raises(runner.FinalRunnerError, match="Role-assignment digest"):
        runner.main(_argv(world, digest))


def test_absent_source_is_refused(world):
    digest = _write_manifest(world)
    world["transactions"].unlink()
    with pytest.raises(runner.FinalRunnerError, match="is not present"):
        runner.main(_argv(world, digest))


def test_role_assignment_digest_mismatch_is_refused(world):
    digest = _write_manifest(world, lambda m: m.update(role_assignment_digest="9" * 64))
    with pytest.raises(runner.FinalRunnerError, match="Role-assignment digest"):
        runner.main(_argv(world, digest))


def test_environment_contract_mismatch_is_refused(world):
    digest = _write_manifest(world, lambda m: m["environment"].update({"numpy": "0.0.0"}))
    with pytest.raises(runner.FinalRunnerError, match="Environment contract"):
        runner.main(_argv(world, digest))


# -- lifecycle refusals --------------------------------------------------


@pytest.mark.parametrize("state", [PREPARED, STARTED, SEALED])
def test_any_prior_lifecycle_state_refuses_a_new_run(world, state):
    digest = _write_manifest(world)
    prior = FinalEvaluationLifecycle(world["private"], freeze_commit=FREEZE, run_id="earlier")
    prior.prepare({})
    if state in (STARTED, SEALED):
        prior.start()
    if state == SEALED:
        prior.seal({})
    with pytest.raises(LifecycleError, match="exactly once"):
        runner.main(_argv(world, digest))


def test_prior_failed_after_access_refuses_a_new_run(world):
    digest = _write_manifest(world)
    prior = FinalEvaluationLifecycle(world["private"], freeze_commit=FREEZE, run_id="earlier")
    prior.prepare({})
    prior.start()
    prior.fail_after_access("earlier failure")
    with pytest.raises(LifecycleError, match="exactly once"):
        runner.main(_argv(world, digest))


def test_final_role_access_cannot_occur_before_started(world, monkeypatch):
    """Feature construction must observe a STARTED lifecycle, never PREPARED."""
    digest = _write_manifest(world)
    observed = {}
    original = runner.build_features

    def spy(*args, **kwargs):
        record = json.loads(
            (world["private"] / "lane_a_final_evaluation_lifecycle.json").read_text()
        )
        observed["state"] = record["state"]
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "build_features", spy)
    runner.main(_argv(world, digest))
    assert observed["state"] == STARTED


def test_failure_after_start_moves_to_failed_after_access(world, monkeypatch):
    digest = _write_manifest(world)

    def explode(*args, **kwargs):
        raise RuntimeError("synthetic failure after access")

    monkeypatch.setattr(runner, "build_features", explode)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        runner.main(_argv(world, digest))
    record = json.loads((world["private"] / "lane_a_final_evaluation_lifecycle.json").read_text())
    assert record["state"] == "FAILED_AFTER_ACCESS"
    assert record["retry_permitted"] is False


# -- ordering: scores sealed before labels -------------------------------


def test_labels_cannot_be_loaded_without_a_score_seal(world):
    with pytest.raises(runner.FinalRunnerError, match="before the score artifacts are sealed"):
        runner._load_labels(world["transactions"], [1, 3], "")


def test_label_misalignment_is_refused(world):
    with pytest.raises(runner.FinalRunnerError, match="do not align"):
        runner._load_labels(world["transactions"], [10 ** 9], "seal")


def test_feature_construction_never_indexes_the_label_column(world):
    final_ids = runner._read_final_ids(world["assignment"])
    frame, order, period = runner.build_features(
        world["transactions"], world["tmp"] / "identity.csv", final_ids
    )
    assert "isFraud" not in frame.columns
    assert frame.shape[1] == 24
    assert order == sorted(order)
    assert len(period) == len(order)


# -- end-to-end synthetic rehearsal --------------------------------------


def test_synthetic_rehearsal_completes_and_seals(world):
    digest = _write_manifest(world)
    export = world["tmp"] / "public.json"
    assert runner.main(_argv(world, digest, public_export=export)) == 0

    record = json.loads((world["private"] / "lane_a_final_evaluation_lifecycle.json").read_text())
    assert record["state"] == SEALED
    assert record["scores_sealed_before_labels"] is True

    seal = json.loads((world["private"] / "final_score_seal.json").read_text())
    assert seal["labels_loaded"] is False
    assert seal["scores_sealed_before_labels"] is True

    public = json.loads(export.read_text())
    assert public["evaluation"] == "IEEE-CIS Lane A final evaluation"
    assert public["selected_variant"] == "E"
    assert [row["daily_review_capacity"] for row in public["capacity_tiers"]] == [
        100,
        250,
        500,
        1_000,
        2_000,
    ]
    metrics = public["metrics"]
    assert metrics["positive_count"] + metrics["negative_count"] == metrics["row_count"]
    assert len(metrics["calibration_table"]) == 15


def test_rehearsal_writes_every_row_level_artifact_outside_the_repository(world):
    digest = _write_manifest(world)
    runner.main(_argv(world, digest))
    for name in (
        "final_features.csv",
        "final_row_order.json",
        "final_raw_scores.json",
        "final_calibrated_scores.json",
        "final_labels.json",
        "final_result_manifest.json",
    ):
        path = world["private"] / name
        assert path.exists()
        assert runner.PROJECT_ROOT not in path.resolve().parents


def test_a_second_execution_is_impossible(world):
    digest = _write_manifest(world)
    assert runner.main(_argv(world, digest)) == 0
    with pytest.raises(LifecycleError, match="exactly once"):
        runner.main(_argv(world, digest))


def test_rehearsal_capacity_rows_reconcile(world):
    digest = _write_manifest(world)
    export = world["tmp"] / "public.json"
    runner.main(_argv(world, digest, public_export=export))
    public = json.loads(export.read_text())
    total = public["metrics"]["row_count"]
    positives = public["metrics"]["positive_count"]
    for row in public["capacity_tiers"]:
        assert row["tp"] + row["fp"] == row["alerts_selected"]
        assert row["tp"] + row["fn"] == positives
        assert row["tp"] + row["fp"] + row["fn"] + row["tn"] == total
        assert row["alerts_selected"] <= row["review_budget"]


def test_result_manifest_binds_the_full_chain(world):
    digest = _write_manifest(world)
    runner.main(_argv(world, digest))
    manifest = json.loads((world["private"] / "final_result_manifest.json").read_text())
    assert manifest["freeze_commit"] == FREEZE
    assert manifest["authorization_manifest_sha256"] == digest
    assert manifest["scores_sealed_before_labels"] is True
    assert manifest["one_run_only"] is True
    assert manifest["post_result_tuning_forbidden"] is True
    assert len(manifest["private_artifacts"]) >= 6


def test_public_export_contains_no_private_path_or_row_values(world):
    digest = _write_manifest(world)
    export = world["tmp"] / "public.json"
    runner.main(_argv(world, digest, public_export=export))
    body = export.read_text()
    assert str(world["private"]) not in body
    assert "isFraud" not in body
    assert "TransactionID" not in body


# -- the rest of Lane A is unchanged -------------------------------------


def test_ordinary_lane_a_paths_still_refuse_the_final_role():
    from src.lane_a.roles import (
        PERMITTED_ROLES,
        RoleNotPermittedError,
        assert_labels_readable,
        assert_role_permitted,
    )

    assert "final_test" not in PERMITTED_ROLES
    for guard in (assert_role_permitted, assert_labels_readable):
        with pytest.raises(RoleNotPermittedError):
            guard("final_test")


def test_materialisers_still_fail_closed_on_the_final_role():
    import scripts.lane_a_materialise_role as materialise_role
    import scripts.lane_a_materialise_variant_superset as materialise_superset
    from src.lane_a.roles import RoleNotPermittedError

    for module in (materialise_role, materialise_superset):
        with pytest.raises(RoleNotPermittedError):
            module.assert_role_permitted("final_test")


# -- access boundary: nothing raw may be touched before STARTED ----------


@pytest.fixture
def boundary_sentinel(world, monkeypatch):
    """Fail if a raw-data path is opened or hashed while the state is not STARTED.

    The lifecycle record on disk is the arbiter: before ``prepare`` there is no
    record at all, after ``prepare`` the state is ``PREPARED``, and only after
    the atomic transition is it ``STARTED``. Any read of the transaction,
    identity or role-assignment files outside the ``STARTED`` window is a
    boundary violation.
    """
    forbidden = {
        world["transactions"].resolve(),
        (world["tmp"] / "identity.csv").resolve(),
        world["assignment"].resolve(),
    }
    lifecycle_path = world["private"] / "lane_a_final_evaluation_lifecycle.json"
    violations: list[tuple[str, str | None]] = []

    original_open = builtins.open
    original_path_open = Path.open
    original_read_bytes = Path.read_bytes
    original_sha = runner.sha256_file

    def current_state() -> str | None:
        try:
            return json.loads(original_path_open(lifecycle_path, encoding="utf-8").read())["state"]
        except (OSError, ValueError, KeyError):
            return None

    def guard(target) -> None:
        try:
            resolved = Path(target).resolve()
        except (TypeError, ValueError, OSError):
            return
        if resolved not in forbidden:
            return
        state = current_state()
        if state != STARTED:
            violations.append((resolved.name, state))
            raise AssertionError(
                f"raw data {resolved.name} accessed while lifecycle state was {state}"
            )

    def fake_open(file, *args, **kwargs):
        guard(file)
        return original_open(file, *args, **kwargs)

    def fake_path_open(self, *args, **kwargs):
        guard(self)
        return original_path_open(self, *args, **kwargs)

    def fake_read_bytes(self):
        guard(self)
        return original_read_bytes(self)

    def fake_sha(path):
        guard(path)
        return original_sha(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(Path, "open", fake_path_open)
    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)
    monkeypatch.setattr(runner, "sha256_file", fake_sha)
    return violations


def test_boundary_sentinel_detects_a_pre_started_read(world, boundary_sentinel):
    """The sentinel must actually fire, or the boundary tests prove nothing."""
    with pytest.raises(AssertionError, match="accessed while lifecycle state was None"):
        world["transactions"].read_bytes()


def test_no_raw_data_is_touched_before_started(world, boundary_sentinel):
    digest = _write_manifest(world)
    assert runner.main(_argv(world, digest)) == 0
    assert boundary_sentinel == []


def test_pre_access_gate_failure_touches_no_raw_data(world, boundary_sentinel):
    """A refused run must not have opened any raw file on its way to refusing."""
    digest = _write_manifest(world, lambda m: m["frozen"].update({"pipeline_sha256": "9" * 64}))
    with pytest.raises(runner.FinalRunnerError):
        runner.main(_argv(world, digest))
    assert boundary_sentinel == []
    assert not (world["private"] / "lane_a_final_evaluation_lifecycle.json").exists()


def test_metadata_gate_runs_before_prepare_and_opens_nothing(world, boundary_sentinel):
    resolved = runner.verify_source_metadata(json.loads(json.dumps(world["manifest"])))
    assert set(resolved) == set(runner.METADATA_ONLY_KEYS)
    assert boundary_sentinel == []


def test_metadata_gate_refuses_a_symlinked_source(world, tmp_path):
    target = tmp_path / "real.csv"
    target.write_text("x\n", encoding="utf-8")
    link = tmp_path / "linked.csv"
    link.symlink_to(target)
    payload = json.loads(json.dumps(world["manifest"]))
    payload["sources"]["identity"]["path"] = str(link)
    with pytest.raises(runner.FinalRunnerError, match="symlink"):
        runner.verify_source_metadata(payload)


def test_metadata_gate_refuses_a_directory_source(world, tmp_path):
    directory = tmp_path / "a_directory"
    directory.mkdir()
    payload = json.loads(json.dumps(world["manifest"]))
    payload["sources"]["identity"]["path"] = str(directory)
    with pytest.raises(runner.FinalRunnerError, match="not a regular file"):
        runner.verify_source_metadata(payload)


def test_byte_verification_is_a_separate_post_started_step(world):
    """The byte gate exists, is distinct, and fails closed on a bad digest."""
    resolved = runner.verify_source_metadata(json.loads(json.dumps(world["manifest"])))
    observed = runner.verify_source_bytes(resolved)
    assert set(observed) == {"transactions", "identity"}


def test_byte_verification_fails_closed_on_a_tampered_source(world, monkeypatch):
    resolved = runner.verify_source_metadata(json.loads(json.dumps(world["manifest"])))
    monkeypatch.setattr(
        runner, "FROZEN_SOURCE_DIGESTS", {**runner.FROZEN_SOURCE_DIGESTS, "identity": "9" * 64}
    )
    with pytest.raises(runner.FinalRunnerError, match="byte digest mismatch"):
        runner.verify_source_bytes(resolved)


def test_role_assignment_content_digest_is_verified_after_started(world, monkeypatch):
    monkeypatch.setattr(
        runner,
        "FROZEN_SOURCE_DIGESTS",
        {**runner.FROZEN_SOURCE_DIGESTS, "role_assignment_digest": "9" * 64},
    )
    with pytest.raises(runner.FinalRunnerError, match="content digest"):
        runner._read_final_ids(world["assignment"])


def test_runner_binds_the_boundary_amendment(world):
    digest = _write_manifest(world, lambda m: m.update(boundary_amendment_sha256="9" * 64))
    with pytest.raises(runner.FinalRunnerError, match="Boundary-amendment digest"):
        runner.main(_argv(world, digest))


def test_result_manifest_records_post_started_byte_verification(world):
    digest = _write_manifest(world)
    runner.main(_argv(world, digest))
    manifest = json.loads((world["private"] / "final_result_manifest.json").read_text())
    assert set(manifest["source_byte_digests_verified_after_started"]) == {
        "transactions",
        "identity",
    }
    assert manifest["boundary_amendment_sha256"] == runner.sha256_file(
        runner.BOUNDARY_AMENDMENT_DOCUMENT
    )


def test_sentinel_would_have_caught_the_original_defect(world, boundary_sentinel):
    """Regression proof for the MT3g-prep boundary defect.

    The original implementation called the byte-verification step before the
    lifecycle existed. Invoking that step outside the STARTED window is exactly
    the old behaviour, and the sentinel must reject it.
    """
    resolved = runner.verify_source_metadata(json.loads(json.dumps(world["manifest"])))
    with pytest.raises(AssertionError, match="accessed while lifecycle state was None"):
        runner.verify_source_bytes(resolved)
    assert [name for name, _ in boundary_sentinel] == ["transactions.csv"]
