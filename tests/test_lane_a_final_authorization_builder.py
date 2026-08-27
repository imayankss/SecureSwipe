"""Boundary tests for the final-authorization manifest builder.

The builder must describe the transaction, identity and role-assignment paths
using metadata only. It must never open, read, hash or parse them during
preparation. These tests install sentinels over every plausible read path and
fail if any of the three files is touched.

Everything here is synthetic. No IEEE-CIS file, no real model artifact and no
``final_test`` row is involved.
"""

from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path

import pytest

import scripts.lane_a_build_final_authorization as builder

FREEZE = "c" * 40


@pytest.fixture
def world(tmp_path):
    """Synthetic sources, artifacts and an MT3e manifest the builder accepts."""
    paths = {}
    for name in ("transactions", "identity", "role_assignment"):
        path = tmp_path / f"{name}.csv"
        path.write_text("TransactionID,role\n1,training\n", encoding="utf-8")
        paths[name] = path
    for name in ("pipeline", "calibrator"):
        path = tmp_path / f"{name}.joblib"
        path.write_bytes(b"synthetic-" + name.encode())
        paths[name] = path

    mt3e = {
        "final_test_touched": False,
        "frontier_digest": "f" * 64,
        "frozen": {
            "selected_schema_digest": "1" * 64,
            "preprocessing_configuration_digest": "2" * 64,
            "xgboost_configuration_digest": "3" * 64,
            "pipeline_sha256": "4" * 64,
            "calibrator_sha256": "5" * 64,
            "calibration_decision_digest": "6" * 64,
            "capacity_policy_digest": "7" * 64,
        },
    }
    mt3e_path = tmp_path / "mt3e.json"
    body = json.dumps(mt3e, indent=2, sort_keys=True)
    mt3e_path.write_text(body, encoding="utf-8")
    paths["mt3e"] = mt3e_path
    paths["mt3e_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    paths["output"] = tmp_path / "authorization.json"
    return paths


def _argv(world):
    return [
        "--freeze-commit", FREEZE,
        "--mt3e-manifest", str(world["mt3e"]),
        "--mt3e-manifest-sha256", world["mt3e_sha256"],
        "--transactions", str(world["transactions"]),
        "--identity", str(world["identity"]),
        "--role-assignment", str(world["role_assignment"]),
        "--pipeline", str(world["pipeline"]),
        "--calibrator", str(world["calibrator"]),
        "--output", str(world["output"]),
    ]


@pytest.fixture
def read_sentinel(world, monkeypatch):
    """Raise if any of the three raw-data paths is opened, read or hashed."""
    forbidden = {
        world["transactions"].resolve(),
        world["identity"].resolve(),
        world["role_assignment"].resolve(),
    }
    touched: list[str] = []

    original_open = builtins.open
    original_path_open = Path.open
    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    original_sha = builder.sha256_file

    def guard(target) -> None:
        try:
            resolved = Path(target).resolve()
        except (TypeError, ValueError, OSError):
            return
        if resolved in forbidden:
            touched.append(str(resolved))
            raise AssertionError(f"Preparation opened a raw-data file: {resolved.name}")

    def fake_open(file, *args, **kwargs):
        guard(file)
        return original_open(file, *args, **kwargs)

    def fake_path_open(self, *args, **kwargs):
        guard(self)
        return original_path_open(self, *args, **kwargs)

    def fake_read_bytes(self):
        guard(self)
        return original_read_bytes(self)

    def fake_read_text(self, *args, **kwargs):
        guard(self)
        return original_read_text(self, *args, **kwargs)

    def fake_sha(path):
        guard(path)
        return original_sha(path)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(Path, "open", fake_path_open)
    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)
    monkeypatch.setattr(Path, "read_text", fake_read_text)
    monkeypatch.setattr(builder, "sha256_file", fake_sha)
    return touched


# -- the sentinel itself must work ---------------------------------------


def test_sentinel_detects_a_deliberate_read(world, read_sentinel):
    with pytest.raises(AssertionError, match="opened a raw-data file"):
        world["transactions"].read_text(encoding="utf-8")


def test_sentinel_allows_unrelated_files(world, read_sentinel):
    assert world["mt3e"].read_text(encoding="utf-8")


# -- the boundary --------------------------------------------------------


def test_builder_never_opens_the_three_raw_data_paths(world, read_sentinel):
    assert builder.main(_argv(world)) == 0
    assert read_sentinel == []


def test_builder_records_metadata_not_a_content_hash(world, read_sentinel):
    builder.main(_argv(world))
    manifest = json.loads(world["output"].read_text(encoding="utf-8"))
    for name in builder.METADATA_ONLY_KEYS:
        entry = manifest["sources"][name]
        assert entry["verified_by"] == "path metadata only during preparation"
        assert entry["byte_verification_stage"] == builder.BYTE_VERIFICATION_STAGE
        assert entry["size_bytes"] == world[name].stat().st_size
        assert "modified_utc" in entry


def test_role_assignment_carries_the_frozen_digest_not_a_file_hash(world, read_sentinel):
    builder.main(_argv(world))
    entry = json.loads(world["output"].read_text(encoding="utf-8"))["sources"]["role_assignment"]
    # The frozen canonical assignment digest is carried, never derived from the
    # supplied file, and no raw file hash is recorded for it at all.
    assert entry["assignment_digest"] == builder.ROLE_ASSIGNMENT_DIGEST
    assert entry["digest_kind"] == "canonical TransactionID,role assignment digest"
    assert "sha256" not in entry
    assert "not recomputed here" in entry["digest_origin"]


def test_source_digests_are_carried_from_the_frozen_record(world, read_sentinel):
    builder.main(_argv(world))
    sources = json.loads(world["output"].read_text(encoding="utf-8"))["sources"]
    assert sources["transactions"]["sha256"] == builder.SOURCE_DIGESTS["transactions"]
    assert sources["identity"]["sha256"] == builder.SOURCE_DIGESTS["identity"]
    for name in ("transactions", "identity"):
        assert "not recomputed here" in sources[name]["digest_origin"]


def test_manifest_states_the_raw_data_access_rule(world, read_sentinel):
    builder.main(_argv(world))
    manifest = json.loads(world["output"].read_text(encoding="utf-8"))
    assert manifest["metadata_only_keys"] == list(builder.METADATA_ONLY_KEYS)
    assert "never opens" in manifest["raw_data_access_rule"]
    assert "STARTED" in manifest["raw_data_access_rule"]


def test_manifest_binds_the_boundary_amendment(world, read_sentinel):
    builder.main(_argv(world))
    manifest = json.loads(world["output"].read_text(encoding="utf-8"))
    amendment = (
        builder.PROJECT_ROOT
        / "docs"
        / "evidence"
        / "LANE_A_FINAL_EVALUATION_PROTOCOL_BOUNDARY_AMENDMENT_1.md"
    )
    assert manifest["boundary_amendment_sha256"] == hashlib.sha256(
        amendment.read_bytes()
    ).hexdigest()


# -- metadata validation still fails closed ------------------------------


def test_absent_raw_data_path_is_refused(world, read_sentinel):
    world["identity"].unlink()
    with pytest.raises(builder.AuthorizationBuildError, match="does not exist"):
        builder.main(_argv(world))


def test_directory_in_place_of_a_raw_data_path_is_refused(world, tmp_path, read_sentinel):
    world["identity"].unlink()
    world["identity"].mkdir()
    with pytest.raises(builder.AuthorizationBuildError, match="not a regular file"):
        builder.main(_argv(world))


def test_symlinked_raw_data_path_is_refused(world, tmp_path, read_sentinel):
    target = tmp_path / "real_identity.csv"
    target.write_text("x\n", encoding="utf-8")
    world["identity"].unlink()
    world["identity"].symlink_to(target)
    with pytest.raises(builder.AuthorizationBuildError, match="symlink"):
        builder.main(_argv(world))


def test_output_inside_the_repository_is_refused(world, read_sentinel):
    argv = _argv(world)
    argv[argv.index(str(world["output"]))] = str(builder.PROJECT_ROOT / "docs" / "leak.json")
    with pytest.raises(builder.AuthorizationBuildError, match="outside the repository"):
        builder.main(argv)


def test_mt3e_manifest_digest_mismatch_is_refused(world, read_sentinel):
    argv = _argv(world)
    argv[argv.index(world["mt3e_sha256"])] = "0" * 64
    with pytest.raises(builder.AuthorizationBuildError, match="does not match"):
        builder.main(argv)


def test_mt3e_manifest_admitting_final_test_access_is_refused(world, tmp_path, read_sentinel):
    payload = json.loads(world["mt3e"].read_text(encoding="utf-8"))
    payload["final_test_touched"] = True
    body = json.dumps(payload, indent=2, sort_keys=True)
    world["mt3e"].write_text(body, encoding="utf-8")
    argv = _argv(world)
    argv[argv.index(world["mt3e_sha256"])] = hashlib.sha256(body.encode()).hexdigest()
    with pytest.raises(builder.AuthorizationBuildError, match="final_test as untouched"):
        builder.main(argv)
