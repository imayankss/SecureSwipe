"""Deterministic provenance manifests for training/evaluation commands."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.artifacts.bundle import sha256_file

RUN_MANIFEST_VERSION = "1"

# Runtime imports and distribution names differ for Linux CPU XGBoost. Keep the
# manifest's stable import-facing name while recording the installed package.
_DISTRIBUTION_ALIASES: dict[str, tuple[str, ...]] = {
    "xgboost": ("xgboost", "xgboost-cpu"),
}


def _git_output(arguments: Sequence[str], repository: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def code_provenance(repository: str | Path) -> dict[str, str | bool | None]:
    """Record commit plus a digest of tracked changes without exposing diff text."""
    root = Path(repository).resolve()
    commit = _git_output(["rev-parse", "HEAD"], root)
    status = _git_output(["status", "--porcelain", "--untracked-files=no"], root)
    diff = _git_output(["diff", "--binary", "HEAD"], root)
    dirty = bool(status)
    return {
        "commit": commit,
        "dirty": dirty,
        "tracked_diff_sha256": (
            hashlib.sha256((diff or "").encode("utf-8")).hexdigest() if dirty else None
        ),
    }


def file_records(files: Mapping[str, str | Path]) -> dict[str, dict[str, str | int]]:
    """Record stable logical names, byte sizes, and SHA-256 values."""
    records: dict[str, dict[str, str | int]] = {}
    for logical_name, raw_path in sorted(files.items()):
        path = Path(raw_path).resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Manifest input is not a regular file: {path}.")
        records[logical_name] = {
            "filename": path.name,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    return records


def runtime_provenance(packages: Sequence[str]) -> dict[str, Any]:
    """Record the exact interpreter/platform/package versions used."""
    dependencies: dict[str, str] = {}
    for package in sorted(set(packages)):
        distribution_names = _DISTRIBUTION_ALIASES.get(package, (package,))
        for distribution_name in distribution_names:
            try:
                dependencies[package] = metadata.version(distribution_name)
                break
            except metadata.PackageNotFoundError:
                continue
        else:
            raise metadata.PackageNotFoundError(package)
    return {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "dependencies": dependencies,
    }


def build_run_manifest(
    *,
    run_kind: str,
    evaluation_scope: str,
    repository: str | Path,
    inputs: Mapping[str, str | Path],
    outputs: Mapping[str, str | Path],
    parameters: Mapping[str, Any],
    seeds: Mapping[str, int],
    packages: Sequence[str],
    data_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Build a timestamp-free manifest whose content changes only with evidence."""
    if not run_kind.strip() or not evaluation_scope.strip():
        raise ValueError("run_kind and evaluation_scope must not be empty.")
    return {
        "code": code_provenance(repository),
        "data_fingerprint": data_fingerprint,
        "evaluation_scope": evaluation_scope,
        "inputs": file_records(inputs),
        "outputs": file_records(outputs),
        "parameters": dict(parameters),
        "run_kind": run_kind,
        "run_manifest_version": RUN_MANIFEST_VERSION,
        "runtime": runtime_provenance(packages),
        "seeds": dict(seeds),
    }


def write_run_manifest(manifest: Mapping[str, Any], output_path: str | Path) -> Path:
    """Write strict, sorted JSON and reject NaN/infinite values."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path
