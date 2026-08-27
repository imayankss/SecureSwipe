"""Lane A one-time final-test evaluation runner.

This is the **only** module in the project permitted to read the ``final_test``
role, and it may do so **exactly once** per freeze commit. Every ordinary Lane A
builder, materialiser and experiment runner continues to fail closed on
``final_test``; nothing here relaxes those guards.

The runner refuses to start unless every digest in the private authorization
manifest matches, and it refuses to start at all if any lifecycle record already
exists for the freeze. There is deliberately no ``--force``, no ``--retry``, no
``--skip-checks``, no fallback model, and no way to alter the frozen capacity
tiers or evaluate variants A-D.

Ordering guarantee: features are built and scored, and the score artifacts are
hashed and sealed, **before** any label is opened. The seal is a precondition of
the label loader, not a convention.

All row-level output is written outside the repository. Only aggregates are
exported publicly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.evaluation.calibration import apply_calibrator  # noqa: E402
from src.lane_a.feature_builder import (  # noqa: E402
    normalise_categorical,
    normalise_numeric,
)
from src.lane_a.final_evaluation import (  # noqa: E402
    CAPACITY_TIERS,
    PREDECLARED_METRICS,
    SELECTED_VARIANT,
    FinalEvaluationError,
    aggregate_metrics,
    assert_metrics_predeclared,
    assert_public_export_safe,
    assert_tiers_frozen,
    assert_variant_selected,
    capacity_table,
    evaluation_period_days,
    recall_80_workload,
)
from src.lane_a.final_lifecycle import (  # noqa: E402
    FinalEvaluationLifecycle,
    LifecycleError,
)
from src.lane_a.serving_schema import (  # noqa: E402
    IDENTITY_PRESENCE_FEATURE,
    NUMERIC_FIELDS,
)
from src.lane_a.variants import SUPERSET_FIELDS, VARIANTS_BY_ID  # noqa: E402

MANIFEST_SCHEMA_VERSION = "lane-a-final-authorization-v1"

#: The authorised final role. Named here, and nowhere else that reads data.
FINAL_ROLE = "final_test"

JOIN_KEY = "TransactionID"
LABEL_COLUMN = "isFraud"
PERIOD_COLUMN = "TransactionDT"
IDENTITY_SOURCED = ("DeviceType", "DeviceInfo")

#: MT3e digests, embedded so a tampered manifest cannot relax them.
FROZEN_DIGESTS: Mapping[str, str] = {
    "selected_schema_digest": "66cfbea1db1fc2c78512de5c15345acbedcdc737b10c4d1bf2ff0b5a0f82ca8d",
    "preprocessing_digest": "0b7168d4a557a4df45a48a4ff886679a6aa3127b0839d255d67c79df2160d3e3",
    "xgboost_configuration_digest": "8fbd438bd15dbec97357798efbe5fb97cb709e457c96419cba520347a8072343",
    "pipeline_sha256": "b6a1429c234bb24a991b685dec9539ce3c5839bff9348947539d68a5ab0d42a0",
    "calibrator_sha256": "5055ca05fab5b490dbb77999774196050ce8b00d9c91166164740b566fadd655",
    "calibration_decision_digest": (
        "876db378c94d006f8d6381f9f5b9efca20cfc837bedfec92c969f802055239cf"
    ),
    "capacity_policy_digest": "6726d4262b84174bc1ed26aafbebbc84c8d512e568880f4f18adc460f45573c3",
    "capacity_frontier_digest": (
        "2da03943d3ebbf6548c1326589b74bd76e9e77783aed976e323ab040355d7575"
    ),
}

#: MT3e source and role-assignment digests.
FROZEN_SOURCE_DIGESTS: Mapping[str, str] = {
    "transactions": "3a5c83ab6b3cc13dcabe5ffa9f522307fd5f7f7b6e6f6a60c32284ca6283d642",
    "identity": "b63c725d8377be90a995268d97f347c17d456b95db45807adcf9f59cd603c37c",
    "role_assignment_digest": (
        "f375cf71aedb6a9b6832678abbafa07f8a0bdc62cc8d6d8851051dd65662f1e4"
    ),
}

PROTOCOL_DOCUMENT = PROJECT_ROOT / "docs" / "evidence" / "LANE_A_FINAL_EVALUATION_PROTOCOL.md"

#: Flags this runner must never accept, checked before argparse.
FORBIDDEN_FLAG_MARKERS: tuple[str, ...] = (
    "--force",
    "--retry",
    "--rerun",
    "--skip",
    "--no-verify",
    "--ignore",
    "--fallback",
    "--variant",
    "--tier",
    "--threshold",
    "--overwrite",
)


class FinalRunnerError(RuntimeError):
    """Raised when the runner refuses to proceed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_bytes(json.dumps(payload, sort_keys=True, default=str).encode())


def assert_no_forbidden_flags(argv: Sequence[str]) -> None:
    """Refuse escape hatches before argparse can silently ignore them."""
    for token in argv:
        lowered = token.lower()
        for marker in FORBIDDEN_FLAG_MARKERS:
            if lowered == marker or lowered.startswith(f"{marker}="):
                raise FinalRunnerError(
                    f"Refusing {token!r}: the final evaluation has no override, retry, "
                    "or reconfiguration path."
                )


def assert_outside_repository(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == PROJECT_ROOT or PROJECT_ROOT in resolved.parents:
        raise FinalRunnerError("Private output must live outside the repository.")
    return resolved


def _require(manifest: Mapping[str, Any], key: str) -> Any:
    if key not in manifest:
        raise FinalRunnerError(f"Authorization manifest is missing {key!r}.")
    return manifest[key]


def load_and_verify_manifest(
    manifest_path: Path,
    expected_manifest_sha256: str,
    expected_freeze_sha: str,
) -> Mapping[str, Any]:
    """Verify the manifest's own digest before trusting any field in it."""
    if not manifest_path.exists():
        raise FinalRunnerError("Authorization manifest not found.")
    observed = sha256_file(manifest_path)
    if observed != expected_manifest_sha256:
        raise FinalRunnerError("Authorization manifest digest does not match the expected value.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise FinalRunnerError(f"Authorization manifest is malformed: {error}") from error
    if not isinstance(manifest, dict):
        raise FinalRunnerError("Authorization manifest is not an object.")
    if _require(manifest, "schema_version") != MANIFEST_SCHEMA_VERSION:
        raise FinalRunnerError("Authorization manifest schema version is not supported.")
    if _require(manifest, "freeze_commit") != expected_freeze_sha:
        raise FinalRunnerError("Authorization manifest is bound to a different freeze commit.")
    if _require(manifest, "final_role") != FINAL_ROLE:
        raise FinalRunnerError("Authorization manifest does not authorise the final role.")
    if _require(manifest, "one_run_only") is not True:
        raise FinalRunnerError("Authorization manifest does not declare a one-run-only rule.")
    if _require(manifest, "post_result_tuning_forbidden") is not True:
        raise FinalRunnerError("Authorization manifest does not forbid post-result tuning.")
    return manifest


def verify_repository_state(expected_freeze_sha: str) -> None:
    head = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        raise FinalRunnerError("Unable to read the repository HEAD.")
    if head.stdout.strip() != expected_freeze_sha:
        raise FinalRunnerError("Repository HEAD does not match the expected freeze commit.")


def verify_frozen_digests(manifest: Mapping[str, Any]) -> None:
    frozen = _require(manifest, "frozen")
    for key, expected in FROZEN_DIGESTS.items():
        if frozen.get(key) != expected:
            raise FinalRunnerError(f"Frozen digest mismatch for {key}.")
    if _require(manifest, "protocol_sha256") != sha256_file(PROTOCOL_DOCUMENT):
        raise FinalRunnerError("Final-evaluation protocol digest does not match the manifest.")
    if _require(manifest, "runner_sha256") != sha256_file(Path(__file__).resolve()):
        raise FinalRunnerError("Runner code digest does not match the manifest.")
    modules = _require(manifest, "module_sha256")
    for name, relative in (
        ("final_evaluation", "src/lane_a/final_evaluation.py"),
        ("final_lifecycle", "src/lane_a/final_lifecycle.py"),
        ("capacity", "src/lane_a/capacity.py"),
        ("variants", "src/lane_a/variants.py"),
    ):
        if modules.get(name) != sha256_file(PROJECT_ROOT / relative):
            raise FinalRunnerError(f"Module digest mismatch for {name}.")


def verify_sources(manifest: Mapping[str, Any]) -> dict[str, Path]:
    sources = _require(manifest, "sources")
    resolved: dict[str, Path] = {}
    for name in ("transactions", "identity", "role_assignment"):
        entry = sources.get(name)
        if not isinstance(entry, dict) or "path" not in entry or "sha256" not in entry:
            raise FinalRunnerError(f"Authorization manifest source entry {name!r} is incomplete.")
        path = Path(str(entry["path"])).expanduser()
        if not path.exists():
            raise FinalRunnerError(f"Authorised source {name!r} is not present.")
        if sha256_file(path) != entry["sha256"]:
            raise FinalRunnerError(f"Source digest mismatch for {name!r}.")
        resolved[name] = path
    for name in ("transactions", "identity"):
        if sources[name]["sha256"] != FROZEN_SOURCE_DIGESTS[name]:
            raise FinalRunnerError(f"Source {name!r} is not the frozen IEEE-CIS artifact.")
    if _require(manifest, "role_assignment_digest") != FROZEN_SOURCE_DIGESTS[
        "role_assignment_digest"
    ]:
        raise FinalRunnerError("Role-assignment digest does not match the frozen partition.")
    return resolved


def verify_artifacts(manifest: Mapping[str, Any]) -> dict[str, Path]:
    artifacts = _require(manifest, "artifacts")
    resolved: dict[str, Path] = {}
    for name, digest_key in (("pipeline", "pipeline_sha256"), ("calibrator", "calibrator_sha256")):
        entry = artifacts.get(name)
        if not isinstance(entry, dict) or "path" not in entry:
            raise FinalRunnerError(f"Authorization manifest artifact {name!r} is incomplete.")
        path = Path(str(entry["path"])).expanduser()
        if not path.exists():
            raise FinalRunnerError(f"Frozen artifact {name!r} is not present.")
        if sha256_file(path) != FROZEN_DIGESTS[digest_key]:
            raise FinalRunnerError(f"Frozen artifact {name!r} digest mismatch.")
        resolved[name] = path
    return resolved


def environment_fingerprint() -> dict[str, str]:
    import sklearn
    import xgboost

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "machine": platform.machine(),
    }


def verify_environment(manifest: Mapping[str, Any]) -> dict[str, str]:
    contract = _require(manifest, "environment")
    observed = environment_fingerprint()
    mismatched = {
        key: (contract[key], observed.get(key))
        for key in contract
        if observed.get(key) != contract[key]
    }
    if mismatched:
        raise FinalRunnerError(f"Environment contract not satisfied: {sorted(mismatched)}.")
    return observed


# -- final-role access ---------------------------------------------------


def _read_final_ids(assignment_path: Path) -> set[int]:
    with assignment_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index, role_index = header.index(JOIN_KEY), header.index("role")
        return {int(row[id_index]) for row in reader if row[role_index] == FINAL_ROLE}


def build_features(
    transactions: Path,
    identity: Path,
    final_ids: set[int],
) -> tuple[pd.DataFrame, list[int], np.ndarray]:
    """Build the frozen variant E representation. Labels are never touched."""
    with identity.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index = header.index(JOIN_KEY)
        columns = {name: header.index(name) for name in IDENTITY_SOURCED}
        identity_rows: dict[int, dict[str, str]] = {}
        for row in reader:
            identifier = int(row[id_index])
            if identifier in final_ids:
                identity_rows[identifier] = {n: row[i] for n, i in columns.items()}

    transaction_sourced = tuple(
        name
        for name in SUPERSET_FIELDS
        if name not in IDENTITY_SOURCED and name != IDENTITY_PRESENCE_FEATURE
    )
    built: list[tuple[int, dict[str, object], float]] = []
    with transactions.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index = header.index(JOIN_KEY)
        period_index = header.index(PERIOD_COLUMN)
        source_index = {name: header.index(name) for name in transaction_sourced}
        # The label column is never indexed, so it cannot be read in this pass.
        if LABEL_COLUMN in source_index:
            raise FinalRunnerError("Label column must not be part of feature construction.")
        for row in reader:
            identifier = int(row[id_index])
            if identifier not in final_ids:
                continue  # no other field of an out-of-role row is touched
            present = identifier in identity_rows
            record: dict[str, object] = {}
            for name in transaction_sourced:
                raw = row[source_index[name]]
                record[name] = (
                    normalise_numeric(name, raw)
                    if name in NUMERIC_FIELDS
                    else normalise_categorical(name, raw)
                )
            for name in IDENTITY_SOURCED:
                raw_identity: str | None = identity_rows[identifier][name] if present else None
                record[name] = normalise_categorical(name, raw_identity)
            record[IDENTITY_PRESENCE_FEATURE] = present
            built.append((identifier, record, float(row[period_index])))

    # Ascending TransactionID is the stable private source position.
    built.sort(key=lambda item: item[0])
    order = [identifier for identifier, _, _ in built]
    period = np.asarray([value for _, _, value in built], dtype=float)
    frame = pd.DataFrame([record for _, record, _ in built], columns=list(SUPERSET_FIELDS))
    variant = VARIANTS_BY_ID[assert_variant_selected(SELECTED_VARIANT)]
    if len(variant.fields) != 24:
        raise FinalRunnerError("Selected variant is not the frozen 24-input schema.")
    return frame[list(variant.fields)], order, period


def _load_labels(transactions: Path, order: Sequence[int], score_seal: str) -> np.ndarray:
    """Load labels. Refuses to run unless the score artifacts are already sealed."""
    if not score_seal:
        raise FinalRunnerError("Labels may not be loaded before the score artifacts are sealed.")
    wanted = set(order)
    labels: dict[int, int] = {}
    with transactions.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        id_index = header.index(JOIN_KEY)
        label_index = header.index(LABEL_COLUMN)
        for row in reader:
            identifier = int(row[id_index])
            if identifier in wanted:
                labels[identifier] = int(row[label_index])
    if len(labels) != len(order):
        raise FinalRunnerError("Label rows do not align with the sealed score rows.")
    return np.asarray([labels[identifier] for identifier in order], dtype=int)


def _write_private(directory: Path, name: str, payload: bytes) -> dict[str, Any]:
    path = directory / name
    path.write_bytes(payload)
    return {"purpose": name, "size_bytes": len(payload), "sha256": sha256_bytes(payload)}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Lane A final-test evaluation exactly once.",
        allow_abbrev=False,
    )
    parser.add_argument("--execute-final-test", action="store_true")
    parser.add_argument("--expected-freeze-sha", required=True)
    parser.add_argument("--authorization-manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--private-output-dir", type=Path, required=True)
    parser.add_argument("--public-export", type=Path, default=None)
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    assert_no_forbidden_flags(raw)
    args = parse_args(raw)

    if not args.execute_final_test:
        raise FinalRunnerError(
            "--execute-final-test is required. This runner never reads final data implicitly."
        )
    if len(args.expected_freeze_sha) != 40:
        raise FinalRunnerError("--expected-freeze-sha must be a full 40-character SHA.")

    private_dir = assert_outside_repository(args.private_output_dir)
    private_dir.mkdir(parents=True, exist_ok=True)
    if args.public_export is not None and args.public_export.suffix != ".json":
        raise FinalRunnerError("--public-export must be a .json aggregate file.")

    # ---- pre-access gates, in order -----------------------------------
    verify_repository_state(args.expected_freeze_sha)
    manifest = load_and_verify_manifest(
        args.authorization_manifest.expanduser(),
        args.expected_manifest_sha256,
        args.expected_freeze_sha,
    )
    verify_frozen_digests(manifest)
    sources = verify_sources(manifest)
    artifacts = verify_artifacts(manifest)
    environment = verify_environment(manifest)
    assert_variant_selected(SELECTED_VARIANT)
    assert_tiers_frozen(CAPACITY_TIERS)
    assert_metrics_predeclared(PREDECLARED_METRICS)

    run_id = str(uuid.uuid4())
    lifecycle = FinalEvaluationLifecycle(
        private_dir, freeze_commit=args.expected_freeze_sha, run_id=run_id
    )
    lifecycle.assert_no_prior_run()

    import joblib

    pipeline = joblib.load(artifacts["pipeline"])
    calibrator = joblib.load(artifacts["calibrator"])

    lifecycle.prepare(
        {
            "authorization_manifest_sha256": args.expected_manifest_sha256,
            "protocol_sha256": manifest["protocol_sha256"],
            "runner_sha256": manifest["runner_sha256"],
            "frozen": dict(manifest["frozen"]),
            "environment": environment,
            "selected_variant": SELECTED_VARIANT,
            "capacity_tiers": list(CAPACITY_TIERS),
            "preflight": "all pre-access gates passed",
        }
    )

    # ---- final-role access begins here --------------------------------
    lifecycle.start({"final_access_begun_utc": _utc_now()})
    started_at = _utc_now()
    try:
        final_ids = _read_final_ids(sources["role_assignment"])
        if not final_ids:
            raise FinalRunnerError("No final-role rows were assigned.")
        features, order, period = build_features(
            sources["transactions"], sources["identity"], final_ids
        )
        if features.shape[1] != 24:
            raise FinalRunnerError("Feature matrix is not the frozen 24-input schema.")
        if len(order) != len(set(order)):
            raise FinalRunnerError("Row order is not unique.")

        raw_scores = pipeline.predict_proba(features)[:, 1]
        calibrated = apply_calibrator(calibrator, raw_scores)
        if not np.all(np.isfinite(calibrated)):
            raise FinalRunnerError("Calibrated output is not finite.")

        period_days = evaluation_period_days(period)

        # ---- seal scores BEFORE any label is opened -------------------
        private_artifacts = [
            _write_private(
                private_dir,
                "final_features.csv",
                features.to_csv(index=False).encode(),
            ),
            _write_private(
                private_dir,
                "final_row_order.json",
                json.dumps(order).encode(),
            ),
            _write_private(
                private_dir,
                "final_raw_scores.json",
                json.dumps([float(v) for v in raw_scores]).encode(),
            ),
            _write_private(
                private_dir,
                "final_calibrated_scores.json",
                json.dumps([float(v) for v in calibrated]).encode(),
            ),
        ]
        score_seal = sha256_json([entry["sha256"] for entry in private_artifacts])
        seal_record = {
            "score_seal_sha256": score_seal,
            "sealed_utc": _utc_now(),
            "labels_loaded": False,
            "scores_sealed_before_labels": True,
        }
        private_artifacts.append(
            _write_private(
                private_dir,
                "final_score_seal.json",
                json.dumps(seal_record, indent=2, sort_keys=True).encode(),
            )
        )

        # ---- labels may now be opened ---------------------------------
        labels = _load_labels(sources["transactions"], order, score_seal)
        private_artifacts.append(
            _write_private(
                private_dir,
                "final_labels.json",
                json.dumps([int(v) for v in labels]).encode(),
            )
        )

        metrics = aggregate_metrics(labels, calibrated)
        tiers = capacity_table(
            labels, calibrated, evaluation_period_days=period_days, tiers=CAPACITY_TIERS
        )
        workload = recall_80_workload(labels, calibrated, evaluation_period_days=period_days)

        public = {
            "evaluation": "IEEE-CIS Lane A final evaluation",
            "freeze_commit": args.expected_freeze_sha,
            "protocol_sha256": manifest["protocol_sha256"],
            "runner_sha256": manifest["runner_sha256"],
            "run_id": run_id,
            "started_utc": started_at,
            "completed_utc": _utc_now(),
            "role_disclosure": "programmatically held out",
            "evaluation_count": "evaluated exactly once",
            "score_terminology": "Platt-calibrated benchmark output",
            "capacity_disclosure": "merchant-configurable illustrative review capacity",
            "evaluation_period_days": round(period_days, 4),
            "selected_variant": SELECTED_VARIANT,
            "metrics": metrics,
            "capacity_tiers": tiers,
            "recall_80_workload": workload,
            "limitations": [
                "not Razorpay economics",
                "not live-merchant performance",
                "not a production SLO",
                "not directly comparable with Lane B",
            ],
        }
        assert_public_export_safe(public)

        result_manifest = {
            "schema_version": "lane-a-final-result-v1",
            "run_id": run_id,
            "freeze_commit": args.expected_freeze_sha,
            "authorization_manifest_sha256": args.expected_manifest_sha256,
            "protocol_sha256": manifest["protocol_sha256"],
            "runner_sha256": manifest["runner_sha256"],
            "module_sha256": dict(manifest["module_sha256"]),
            "frozen": dict(manifest["frozen"]),
            "role_assignment_digest": manifest["role_assignment_digest"],
            "environment": environment,
            "private_artifacts": private_artifacts,
            "score_seal_sha256": score_seal,
            "scores_sealed_before_labels": True,
            "aggregate_metrics": metrics,
            "capacity_tiers": tiers,
            "recall_80_workload": workload,
            "started_utc": started_at,
            "completed_utc": _utc_now(),
            "one_run_only": True,
            "post_result_tuning_forbidden": True,
        }
        private_artifacts.append(
            _write_private(
                private_dir,
                "final_result_manifest.json",
                json.dumps(result_manifest, indent=2, sort_keys=True, default=str).encode(),
            )
        )

        lifecycle.seal(
            {
                "result_manifest_sha256": private_artifacts[-1]["sha256"],
                "score_seal_sha256": score_seal,
                "scores_sealed_before_labels": True,
            }
        )
    except BaseException as error:  # noqa: BLE001 - preserved then re-raised
        lifecycle.fail_after_access(f"{type(error).__name__}: {error}")
        raise

    if args.public_export is not None:
        args.public_export.write_text(
            json.dumps(public, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
    print(json.dumps(public, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        raise SystemExit(main())
    except (FinalRunnerError, FinalEvaluationError, LifecycleError) as failure:
        print(f"REFUSED: {failure}", file=sys.stderr)
        raise SystemExit(2) from failure
