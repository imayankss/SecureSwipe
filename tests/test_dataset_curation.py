"""Deterministic curation and historical-taint boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import scripts.curate_dataset as curation_script
from scripts.curate_dataset import curate_dataset
from src.data.curation import curate_exact_feature_duplicates, load_curated_dataset
from src.preprocessing.feature_config import REQUIRED_COLUMNS
from tests.source_approval_helpers import write_source_approval


def _frame(rows: int = 24) -> pd.DataFrame:
    values: dict[str, np.ndarray] = {"Time": np.arange(rows, dtype=float)}
    for index in range(1, 29):
        values[f"V{index}"] = np.arange(rows, dtype=float) + index / 100
    values["Amount"] = np.arange(rows, dtype=float) + 1
    values["Class"] = np.array(([0, 0, 1] * (rows // 3 + 1))[:rows])
    return pd.DataFrame(values, columns=REQUIRED_COLUMNS)


def test_curation_is_deterministic_and_records_removed_class_counts(tmp_path: Path) -> None:
    raw = _frame()
    raw = pd.concat([raw, raw.iloc[[2]], raw.iloc[[4]]], ignore_index=True)
    source = tmp_path / "authorized.csv"
    raw.to_csv(source, index=False)
    approval = write_source_approval(source, "fixture-new-source-v1")
    first = curate_dataset(
        source_path=source,
        output_dir=tmp_path / "first",
        source_kind="new_authorized_development",
        source_reference="fixture-new-source-v1",
        source_approval_path=approval,
    )
    second = curate_dataset(
        source_path=source,
        output_dir=tmp_path / "second",
        source_kind="new_authorized_development",
        source_reference="fixture-new-source-v1",
        source_approval_path=approval,
    )

    first_record = json.loads(first["curation_record"].read_text(encoding="utf-8"))
    second_record = json.loads(second["curation_record"].read_text(encoding="utf-8"))
    assert first_record == second_record
    assert first_record["removed_rows"] == 2
    assert first_record["removed_fraud"] == 1
    assert first_record["removed_legitimate"] == 1
    assert first_record["decision_eligible"] is True
    assert first["curated_dataset"].read_bytes() == second["curated_dataset"].read_bytes()


def test_conflicting_duplicate_labels_fail_without_publishing(tmp_path: Path) -> None:
    raw = _frame()
    conflict = raw.iloc[[0]].copy()
    conflict["Class"] = 1
    combined = pd.concat([raw, conflict], ignore_index=True)
    with pytest.raises(ValueError, match="conflicting Class labels"):
        curate_exact_feature_duplicates(combined)


def test_configured_historical_path_cannot_be_declared_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "creditcard.csv"
    _frame().to_csv(source, index=False)
    monkeypatch.setattr(curation_script, "PROJECT_ROOT", tmp_path)
    replacement = curation_script.CONFIG.model_copy(
        update={
            "data": curation_script.CONFIG.data.model_copy(
                update={"raw_path": Path("creditcard.csv")}
            )
        }
    )
    monkeypatch.setattr(curation_script, "CONFIG", replacement)
    with pytest.raises(ValueError, match="already test-observed"):
        approval = write_source_approval(source, "renamed-copy")
        curate_dataset(
            source_path=source,
            output_dir=tmp_path / "output",
            source_kind="new_authorized_development",
            source_reference="renamed-copy",
            source_approval_path=approval,
        )


def test_known_historical_signature_is_reference_only_even_when_renamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "renamed.csv"
    _frame().to_csv(source, index=False)
    monkeypatch.setattr(curation_script, "KNOWN_HISTORICAL_ROWS", 24)
    monkeypatch.setattr(curation_script, "KNOWN_HISTORICAL_FRAUD", 8)
    with pytest.raises(ValueError, match="reference-only even if copied or renamed"):
        approval = write_source_approval(source, "renamed-copy")
        curate_dataset(
            source_path=source,
            output_dir=tmp_path / "output",
            source_kind="new_authorized_development",
            source_reference="renamed-copy",
            source_approval_path=approval,
        )


def test_new_source_requires_checksum_bound_operator_approval(tmp_path: Path) -> None:
    source = tmp_path / "new.csv"
    _frame().to_csv(source, index=False)
    with pytest.raises(ValueError, match="operator-reviewed source approval"):
        curate_dataset(
            source_path=source,
            output_dir=tmp_path / "missing",
            source_kind="new_authorized_development",
            source_reference="approved-v1",
        )
    approval = write_source_approval(source, "approved-v1")
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not bound to these exact source bytes"):
        curate_dataset(
            source_path=source,
            output_dir=tmp_path / "tampered",
            source_kind="new_authorized_development",
            source_reference="approved-v1",
            source_approval_path=approval,
        )


def test_historical_curated_derivative_cannot_be_promoted(tmp_path: Path) -> None:
    source = tmp_path / "historical.csv"
    raw = pd.concat([_frame(), _frame().iloc[[0]]], ignore_index=True)
    raw.to_csv(source, index=False)
    historical = curate_dataset(
        source_path=source,
        output_dir=tmp_path / "historical-curated",
        source_kind="historical_kaggle_reference",
        source_reference="historical-fixture",
    )
    approval = write_source_approval(
        historical["curated_dataset"], "attempted-promotion"
    )
    with pytest.raises(ValueError, match="historical-tainted curated derivative"):
        curate_dataset(
            source_path=historical["curated_dataset"],
            output_dir=tmp_path / "promoted",
            source_kind="new_authorized_development",
            source_reference="attempted-promotion",
            source_approval_path=approval,
        )


def test_curation_manifest_and_approval_provenance_are_verified(tmp_path: Path) -> None:
    source = tmp_path / "new.csv"
    _frame().to_csv(source, index=False)
    reference = "reviewed-new-v1"
    approval = write_source_approval(source, reference)
    curated = curate_dataset(
        source_path=source,
        output_dir=tmp_path / "curated",
        source_kind="new_authorized_development",
        source_reference=reference,
        source_approval_path=approval,
    )
    load_curated_dataset(
        curated["curated_dataset"],
        curated["curation_record"],
        require_decision_eligible=True,
    )

    manifest = json.loads(curated["run_manifest"].read_text(encoding="utf-8"))
    manifest["parameters"]["source_reference"] = "substituted-source"
    curated["run_manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="source provenance is inconsistent"):
        load_curated_dataset(
            curated["curated_dataset"],
            curated["curation_record"],
            require_decision_eligible=True,
        )


def test_source_approval_requires_exact_reference_and_attestation(tmp_path: Path) -> None:
    source = tmp_path / "new.csv"
    _frame().to_csv(source, index=False)
    approval = write_source_approval(source, "approved-v1")
    with pytest.raises(ValueError, match="reference does not match"):
        curate_dataset(
            source_path=source,
            output_dir=tmp_path / "wrong-reference",
            source_kind="new_authorized_development",
            source_reference="approved-v2",
            source_approval_path=approval,
        )
    payload = json.loads(approval.read_text(encoding="utf-8"))
    payload["attestation"] = "trust me"
    approval.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="required attestation"):
        curate_dataset(
            source_path=source,
            output_dir=tmp_path / "wrong-attestation",
            source_kind="new_authorized_development",
            source_reference="approved-v1",
            source_approval_path=approval,
        )
