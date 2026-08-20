"""Regression tests for runtime manifest package metadata."""

from __future__ import annotations

from importlib import metadata

from src.utils.run_manifest import runtime_provenance


def test_xgb_cpu_metadata(monkeypatch) -> None:
    def version(distribution_name: str) -> str:
        if distribution_name == "xgboost":
            raise metadata.PackageNotFoundError(distribution_name)
        if distribution_name == "xgboost-cpu":
            return "3.3.0"
        raise AssertionError(distribution_name)

    monkeypatch.setattr(metadata, "version", version)

    assert runtime_provenance(["xgboost"])["dependencies"] == {"xgboost": "3.3.0"}
