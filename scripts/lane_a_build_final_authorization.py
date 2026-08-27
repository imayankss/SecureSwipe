"""Build the private Lane A final-evaluation authorization manifest.

Run this **after** the preparation freeze commit exists. It binds the new commit,
the frozen protocol, the runner, the frozen MT3e digests, the approved private
artifact locations, and the environment contract into a single private manifest
that the one-time runner verifies before it will start.

This helper never reads ``final_test`` and never computes a metric.

**Preparation is metadata-only for raw data.** The transaction, identity and
role-assignment paths are validated by existence, regular-file check, symlink
rejection, canonical resolution, size and modification time. They are never
opened, read, hashed, parsed, previewed or counted here. Their frozen digests
are carried from the verified frozen record, never recomputed, so preparation
cannot silently re-derive a frozen value. Byte-level verification of those files
happens only after the private lifecycle has atomically entered ``STARTED``.

See ``docs/evidence/LANE_A_FINAL_EVALUATION_PROTOCOL_BOUNDARY_AMENDMENT_1.md``.

Every private location is supplied on the command line. No private path is
hardcoded here, and the manifest itself is written outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MANIFEST_SCHEMA_VERSION = "lane-a-final-authorization-v1"
MT3E_FREEZE_COMMIT = "8f8e36955c1d7b0ca4ee233ac4864d5fcc6428b9"
FINAL_ROLE = "final_test"

#: Digest keys copied verbatim out of the private MT3e aggregate manifest.
MT3E_DIGEST_KEYS: Mapping[str, str] = {
    "selected_schema_digest": "selected_schema_digest",
    "preprocessing_digest": "preprocessing_configuration_digest",
    "xgboost_configuration_digest": "xgboost_configuration_digest",
    "pipeline_sha256": "pipeline_sha256",
    "calibrator_sha256": "calibrator_sha256",
    "calibration_decision_digest": "calibration_decision_digest",
    "capacity_policy_digest": "capacity_policy_digest",
}

#: Published source digests. Recorded, never recomputed from the raw files.
SOURCE_DIGESTS: Mapping[str, str] = {
    "transactions": "3a5c83ab6b3cc13dcabe5ffa9f522307fd5f7f7b6e6f6a60c32284ca6283d642",
    "identity": "b63c725d8377be90a995268d97f347c17d456b95db45807adcf9f59cd603c37c",
}
ROLE_ASSIGNMENT_DIGEST = "f375cf71aedb6a9b6832678abbafa07f8a0bdc62cc8d6d8851051dd65662f1e4"

#: Paths that preparation may only ever describe, never open.
METADATA_ONLY_KEYS: tuple[str, ...] = ("transactions", "identity", "role_assignment")

#: Where byte-level verification of those paths is permitted to happen.
BYTE_VERIFICATION_STAGE = "after the lifecycle atomically enters STARTED"

#: Public output keys the runner is permitted to export.
PUBLIC_OUTPUT_SCHEMA: tuple[str, ...] = (
    "evaluation",
    "freeze_commit",
    "protocol_sha256",
    "runner_sha256",
    "run_id",
    "started_utc",
    "completed_utc",
    "role_disclosure",
    "evaluation_count",
    "score_terminology",
    "capacity_disclosure",
    "evaluation_period_days",
    "selected_variant",
    "metrics",
    "capacity_tiers",
    "recall_80_workload",
    "limitations",
)

TRACKED_MODULES: Mapping[str, str] = {
    "final_evaluation": "src/lane_a/final_evaluation.py",
    "final_lifecycle": "src/lane_a/final_lifecycle.py",
    "capacity": "src/lane_a/capacity.py",
    "variants": "src/lane_a/variants.py",
}


class AuthorizationBuildError(RuntimeError):
    """Raised when the manifest cannot be built safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_metadata(path: Path, *, name: str) -> dict[str, Any]:
    """Describe a raw-data path without ever opening it.

    Only stat-level operations are used: symlink rejection, existence, a
    regular-file check, canonical resolution, size and modification time. This
    function must never open, read, hash or parse the file. Byte-level
    verification of these paths is deferred until after ``STARTED``.
    """
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise AuthorizationBuildError(
            f"Authorised {name} location is a symlink; refusing to record it."
        )
    if not candidate.exists():
        raise AuthorizationBuildError(f"Authorised {name} location does not exist.")
    if not candidate.is_file():
        raise AuthorizationBuildError(f"Authorised {name} location is not a regular file.")
    resolved = candidate.resolve()
    stat_result = resolved.stat()
    return {
        "path": str(resolved),
        "size_bytes": stat_result.st_size,
        "modified_utc": datetime.fromtimestamp(stat_result.st_mtime, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "verified_by": "path metadata only during preparation",
        "byte_verification_stage": BYTE_VERIFICATION_STAGE,
    }


def environment_contract() -> dict[str, str]:
    import numpy
    import pandas
    import sklearn
    import xgboost

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scikit_learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "machine": platform.machine(),
    }


def _frozen_from_mt3e(mt3e: Mapping[str, Any]) -> dict[str, str]:
    frozen = mt3e.get("frozen")
    if not isinstance(frozen, dict):
        raise AuthorizationBuildError("MT3e manifest has no frozen block.")
    resolved: dict[str, str] = {}
    for target, source_key in MT3E_DIGEST_KEYS.items():
        value = frozen.get(source_key)
        if not isinstance(value, str) or len(value) != 64:
            raise AuthorizationBuildError(f"MT3e manifest is missing {source_key!r}.")
        resolved[target] = value
    frontier = mt3e.get("frontier_digest")
    if not isinstance(frontier, str) or len(frontier) != 64:
        raise AuthorizationBuildError("MT3e manifest is missing frontier_digest.")
    resolved["capacity_frontier_digest"] = frontier
    return resolved


def build(args: argparse.Namespace) -> dict[str, Any]:
    mt3e_path = args.mt3e_manifest.expanduser()
    if sha256_file(mt3e_path) != args.mt3e_manifest_sha256:
        raise AuthorizationBuildError("MT3e manifest digest does not match the expected value.")
    mt3e = json.loads(mt3e_path.read_text(encoding="utf-8"))
    if mt3e.get("final_test_touched") is not False:
        raise AuthorizationBuildError("MT3e manifest does not record final_test as untouched.")

    protocol = PROJECT_ROOT / "docs" / "evidence" / "LANE_A_FINAL_EVALUATION_PROTOCOL.md"
    amendment = (
        PROJECT_ROOT
        / "docs"
        / "evidence"
        / "LANE_A_FINAL_EVALUATION_PROTOCOL_BOUNDARY_AMENDMENT_1.md"
    )
    runner = PROJECT_ROOT / "scripts" / "lane_a_run_final_evaluation.py"
    for path in (protocol, amendment, runner):
        if not path.exists():
            raise AuthorizationBuildError(f"Required committed file is missing: {path.name}")

    # Model artifacts may be described by existence here; the runner verifies
    # their digests. Raw data paths go through metadata-only validation below.
    for name, path in (("pipeline", args.pipeline), ("calibrator", args.calibrator)):
        if not path.expanduser().exists():
            raise AuthorizationBuildError(f"Authorised {name} location does not exist.")

    frozen = _frozen_from_mt3e(mt3e)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "freeze_commit": args.freeze_commit,
        "mt3e_freeze_commit": MT3E_FREEZE_COMMIT,
        "mt3e_manifest_sha256": args.mt3e_manifest_sha256,
        "final_role": FINAL_ROLE,
        "selected_variant": "E",
        "protocol_sha256": sha256_file(protocol),
        "boundary_amendment_sha256": sha256_file(amendment),
        "runner_sha256": sha256_file(runner),
        "module_sha256": {
            name: sha256_file(PROJECT_ROOT / relative)
            for name, relative in TRACKED_MODULES.items()
        },
        "frozen": frozen,
        "role_assignment_digest": ROLE_ASSIGNMENT_DIGEST,
        "sources": {
            "transactions": {
                **path_metadata(args.transactions, name="transactions"),
                "sha256": SOURCE_DIGESTS["transactions"],
                "digest_origin": "committed IEEE-CIS intake record; not recomputed here",
            },
            "identity": {
                **path_metadata(args.identity, name="identity"),
                "sha256": SOURCE_DIGESTS["identity"],
                "digest_origin": "committed IEEE-CIS intake record; not recomputed here",
            },
            "role_assignment": {
                **path_metadata(args.role_assignment, name="role_assignment"),
                "assignment_digest": ROLE_ASSIGNMENT_DIGEST,
                "digest_kind": "canonical TransactionID,role assignment digest",
                "digest_origin": "committed partition freeze record; not recomputed here",
            },
        },
        "metadata_only_keys": list(METADATA_ONLY_KEYS),
        "raw_data_access_rule": (
            "Preparation never opens, reads, hashes or parses the transaction, identity "
            "or role-assignment files. Byte-level verification of those files happens "
            f"{BYTE_VERIFICATION_STAGE}."
        ),
        "artifacts": {
            "pipeline": {"path": str(args.pipeline.expanduser())},
            "calibrator": {"path": str(args.calibrator.expanduser())},
        },
        "environment": environment_contract(),
        "capacity_tiers": [100, 250, 500, 1000, 2000],
        "one_run_only": True,
        "lifecycle_rule": (
            "PREPARED -> STARTED -> (SEALED | FAILED_AFTER_ACCESS); STARTED is written "
            "immediately before first final-role access and is never rerun or retried."
        ),
        "public_output_schema": list(PUBLIC_OUTPUT_SCHEMA),
        "post_result_tuning_forbidden": True,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the private Lane A final-evaluation authorization manifest.",
        allow_abbrev=False,
    )
    parser.add_argument("--freeze-commit", required=True)
    parser.add_argument("--mt3e-manifest", type=Path, required=True)
    parser.add_argument("--mt3e-manifest-sha256", required=True)
    parser.add_argument("--transactions", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--role-assignment", type=Path, required=True)
    parser.add_argument("--pipeline", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if len(args.freeze_commit) != 40:
        raise AuthorizationBuildError("--freeze-commit must be a full 40-character SHA.")
    output = args.output.expanduser().resolve()
    if output == PROJECT_ROOT or PROJECT_ROOT in output.parents:
        raise AuthorizationBuildError("The authorization manifest must be written outside the repository.")

    manifest = build(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(manifest, indent=2, sort_keys=True)
    output.write_text(body, encoding="utf-8")

    # Purpose, size and digest only. The path is never printed.
    print(
        json.dumps(
            {
                "purpose": "Lane A final-evaluation authorization manifest",
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "freeze_commit": manifest["freeze_commit"],
                "runner_sha256": manifest["runner_sha256"],
                "protocol_sha256": manifest["protocol_sha256"],
                "boundary_amendment_sha256": manifest["boundary_amendment_sha256"],
                "size_bytes": len(body.encode()),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "final_test_read": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except AuthorizationBuildError as failure:
        print(f"REFUSED: {failure}", file=sys.stderr)
        raise SystemExit(2) from failure
