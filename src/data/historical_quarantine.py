"""Hash-only quarantine boundary for the already-observed historical test set."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Iterator

import numpy as np
import pandas as pd

from src.artifacts.bundle import sha256_file
from src.data.data_loader import validate_dataset_schema
from src.preprocessing.feature_config import ALL_FEATURES, REQUIRED_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORICAL_QUARANTINE_ANCHOR = (
    PROJECT_ROOT / "configs" / "historical_test_quarantine_anchor.json"
)
HISTORICAL_QUARANTINE_FORMAT_VERSION = "1"
HISTORICAL_QUARANTINE_ANCHOR_FORMAT_VERSION = "1"
HISTORICAL_QUARANTINE_ANCHOR_CANDIDATE_FORMAT_VERSION = "1"
HISTORICAL_TEST_ROWS = 42_722
HISTORICAL_TEST_FRAUD = 74
ROW_HASH_ALGORITHM = "sha256-canonical-float64-le-class-uint8-v1"
MANIFEST_SERIALIZATION = "json-utf8-indent-2-sort-keys-newline-v1"
FEATURE_DTYPE = "float64"
TARGET_DTYPE = "int64"
_ROW_HASH_DOMAIN = b"SecureSwipe historical test quarantine row v1\x00"
_HASH_LIST_DOMAIN = b"SecureSwipe historical quarantine manifest hashes v1\x00"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


def _dtype_contract() -> dict[str, object]:
    return {
        "features": {feature: FEATURE_DTYPE for feature in ALL_FEATURES},
        "target": {"Class": TARGET_DTYPE},
    }


@dataclass(frozen=True)
class HistoricalQuarantineAnchor:
    """Approved identity of the one canonical historical-test quarantine."""

    source_sha256: dict[str, str]
    row_hashes_sha256: str
    total_row_count: int
    fraud_count: int
    unique_row_count: int
    duplicate_row_count: int
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class HistoricalTestQuarantine:
    """Validated hash-only representation of historical test rows."""

    row_hashes: frozenset[str]
    total_row_count: int
    fraud_count: int
    unique_row_count: int
    duplicate_row_count: int
    row_hashes_sha256: str
    manifest_path: Path
    manifest_sha256: str
    manifest_size_bytes: int
    anchor_path: Path
    anchor_sha256: str
    anchor_size_bytes: int


def _is_exact_dtype(dtype: object, expected: str) -> bool:
    try:
        return np.dtype(dtype) == np.dtype(expected)
    except TypeError:
        return False


def _validate_exact_dtypes(frame: pd.DataFrame) -> None:
    wrong_features = {
        feature: str(frame[feature].dtype)
        for feature in ALL_FEATURES
        if feature in frame and not _is_exact_dtype(frame[feature].dtype, FEATURE_DTYPE)
    }
    if wrong_features:
        raise ValueError(
            "Historical quarantine features must use exact float64 dtypes; "
            f"found {wrong_features}."
        )
    if "Class" in frame and not _is_exact_dtype(frame["Class"].dtype, TARGET_DTYPE):
        raise ValueError(
            "Historical quarantine Class must use the exact predeclared "
            f"{TARGET_DTYPE} dtype; found {frame['Class'].dtype}."
        )


def canonical_row_hashes(frame: pd.DataFrame) -> list[str]:
    """Hash canonical float64 values plus one validated binary class byte."""
    _validate_exact_dtypes(frame)
    validate_dataset_schema(frame, reject_duplicate_rows=False)
    feature_values = frame[ALL_FEATURES].to_numpy(copy=True)
    features = np.ascontiguousarray(feature_values, dtype=np.dtype("<f8"))
    labels = frame["Class"].to_numpy(copy=True)
    hashes: list[str] = []
    for index, label in enumerate(labels):
        digest = hashlib.sha256(_ROW_HASH_DOMAIN)
        digest.update(features[index].tobytes(order="C"))
        digest.update(bytes((int(label),)))
        hashes.append(digest.hexdigest())
    return hashes


def row_hashes_checksum(row_hashes: list[str]) -> str:
    """Digest a sorted hash multiset using fixed-width records and separators."""
    ordered = sorted(row_hashes)
    if any(not _SHA256_PATTERN.fullmatch(value) for value in ordered):
        raise ValueError("Historical quarantine row hashes must be lowercase SHA-256 values.")
    digest = hashlib.sha256(_HASH_LIST_DOMAIN)
    for row_hash in ordered:
        digest.update(row_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _regular_file(path: str | Path, *, label: str, suffix: str) -> Path:
    source = Path(path).expanduser()
    if source.is_symlink():
        raise ValueError(f"{label} must not be a symbolic link.")
    resolved = source.resolve(strict=True)
    if not resolved.is_file() or resolved.suffix.lower() != suffix:
        raise ValueError(f"{label} must be a regular {suffix} file.")
    return resolved


def _stable_file_identity(path: Path) -> tuple[str, int]:
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise ValueError(f"Input changed while its identity was being hashed: {path.name}.")
    return digest, after.st_size


def _read_aligned_historical_split(
    x_test_path: Path, y_test_path: Path
) -> tuple[pd.DataFrame, dict[str, dict[str, str | int]]]:
    x_path = _regular_file(x_test_path, label="x_test_path", suffix=".parquet")
    y_path = _regular_file(y_test_path, label="y_test_path", suffix=".parquet")
    before = {
        "x_test": _stable_file_identity(x_path),
        "y_test": _stable_file_identity(y_path),
    }
    x_test = pd.read_parquet(x_path)
    y_test = pd.read_parquet(y_path)
    after = {
        "x_test": _stable_file_identity(x_path),
        "y_test": _stable_file_identity(y_path),
    }
    if before != after:
        raise ValueError("Historical split inputs changed while they were being read.")
    if not isinstance(x_test, pd.DataFrame) or list(x_test.columns) != list(ALL_FEATURES):
        raise ValueError("Historical X_test must use the canonical ALL_FEATURES schema/order.")
    if not isinstance(y_test, pd.DataFrame) or list(y_test.columns) != ["Class"]:
        raise ValueError("Historical y_test must contain only the canonical Class column.")
    _validate_exact_dtypes(x_test)
    _validate_exact_dtypes(y_test)
    if len(x_test) != len(y_test) or not x_test.index.equals(y_test.index):
        raise ValueError("Historical X_test and y_test rows are not exactly aligned.")
    if not x_test.index.is_unique or not y_test.index.is_unique:
        raise ValueError("Historical X_test and y_test indices must be unique.")

    frame = x_test.copy()
    frame["Class"] = y_test["Class"]
    frame = frame[REQUIRED_COLUMNS]
    _validate_exact_dtypes(frame)
    validate_dataset_schema(frame, reject_duplicate_rows=False)
    sources = {
        "x_test": {
            "filename": _safe_basename(x_path.name),
            "sha256": before["x_test"][0],
            "size_bytes": before["x_test"][1],
        },
        "y_test": {
            "filename": _safe_basename(y_path.name),
            "sha256": before["y_test"][0],
            "size_bytes": before["y_test"][1],
        },
    }
    return frame, sources


def _safe_basename(value: object) -> str:
    if not isinstance(value, str) or not value or value in {".", ".."}:
        raise ValueError("Manifest filenames must be non-empty basenames.")
    if (
        "/" in value
        or "\\" in value
        or Path(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or bool(PureWindowsPath(value).drive)
        or Path(value).name != value
    ):
        raise ValueError("Manifest filenames must not contain paths or path separators.")
    return value


def _read_json_bytes(
    path: str | Path, *, label: str
) -> tuple[dict[str, Any], Path, str, int]:
    source = _regular_file(path, label=label, suffix=".json")
    encoded = source.read_bytes()
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    return payload, source, hashlib.sha256(encoded).hexdigest(), len(encoded)


def load_historical_quarantine_anchor() -> HistoricalQuarantineAnchor:
    """Load the tracked approval anchor, refusing its bootstrap state."""
    payload, path, digest, size_bytes = _read_json_bytes(
        DEFAULT_HISTORICAL_QUARANTINE_ANCHOR,
        label="Historical quarantine anchor",
    )
    required = {
        "anchor_format_version",
        "approval_status",
        "quarantine_format_version",
        "row_hash_algorithm",
        "dtype_contract",
        "source_sha256",
        "row_hashes_sha256",
        "total_row_count",
        "fraud_count",
        "unique_row_count",
        "duplicate_row_count",
        "reviewed_by",
        "review_reference",
    }
    if set(payload) != required:
        raise ValueError("Historical quarantine anchor fields are incomplete or unexpected.")
    if (
        payload["anchor_format_version"] != HISTORICAL_QUARANTINE_ANCHOR_FORMAT_VERSION
        or payload["quarantine_format_version"]
        != HISTORICAL_QUARANTINE_FORMAT_VERSION
        or payload["row_hash_algorithm"] != ROW_HASH_ALGORITHM
        or payload["dtype_contract"] != _dtype_contract()
    ):
        raise ValueError("Historical quarantine anchor contract mismatch.")
    if payload["approval_status"] != "approved":
        raise ValueError(
            "Historical quarantine anchor is not populated and independently approved."
        )
    source_sha256 = payload["source_sha256"]
    counts = (
        payload["total_row_count"],
        payload["fraud_count"],
        payload["unique_row_count"],
        payload["duplicate_row_count"],
    )
    if (
        not isinstance(source_sha256, dict)
        or set(source_sha256) != {"x_test", "y_test"}
        or any(
            not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value)
            for value in source_sha256.values()
        )
        or not isinstance(payload["row_hashes_sha256"], str)
        or not _SHA256_PATTERN.fullmatch(payload["row_hashes_sha256"])
        or any(type(value) is not int for value in counts)
        or payload["total_row_count"] <= 0
        or not 0 <= payload["fraud_count"] <= payload["total_row_count"]
        or not 0 < payload["unique_row_count"] <= payload["total_row_count"]
        or payload["duplicate_row_count"]
        != payload["total_row_count"] - payload["unique_row_count"]
        or (
            payload["total_row_count"] != HISTORICAL_TEST_ROWS
            or payload["fraud_count"] != HISTORICAL_TEST_FRAUD
        )
        or not isinstance(payload["reviewed_by"], str)
        or not payload["reviewed_by"].strip()
        or not isinstance(payload["review_reference"], str)
        or not payload["review_reference"].strip()
    ):
        raise ValueError("Historical quarantine anchor approval values are malformed.")
    return HistoricalQuarantineAnchor(
        source_sha256=dict(source_sha256),
        row_hashes_sha256=payload["row_hashes_sha256"],
        total_row_count=payload["total_row_count"],
        fraud_count=payload["fraud_count"],
        unique_row_count=payload["unique_row_count"],
        duplicate_row_count=payload["duplicate_row_count"],
        path=path,
        sha256=digest,
        size_bytes=size_bytes,
    )


def _require_anchor_match(
    payload: dict[str, Any], anchor: HistoricalQuarantineAnchor
) -> None:
    sources = payload["sources"]
    if (
        payload["format_version"] != HISTORICAL_QUARANTINE_FORMAT_VERSION
        or payload["row_hashes_sha256"] != anchor.row_hashes_sha256
        or payload["total_row_count"] != anchor.total_row_count
        or payload["fraud_count"] != anchor.fraud_count
        or payload["unique_row_count"] != anchor.unique_row_count
        or payload["duplicate_row_count"] != anchor.duplicate_row_count
        or sources["x_test"]["sha256"] != anchor.source_sha256["x_test"]
        or sources["y_test"]["sha256"] != anchor.source_sha256["y_test"]
    ):
        raise ValueError(
            "Historical quarantine manifest does not match the approved canonical anchor."
        )


def _build_historical_quarantine_payload(
    *,
    x_test_path: Path,
    y_test_path: Path,
) -> dict[str, Any]:
    frame, sources = _read_aligned_historical_split(x_test_path, y_test_path)
    row_hashes = sorted(canonical_row_hashes(frame))
    unique_row_count = len(set(row_hashes))
    return {
        "format_version": HISTORICAL_QUARANTINE_FORMAT_VERSION,
        "manifest_kind": "historical_test_row_quarantine",
        "feature_schema": list(ALL_FEATURES),
        "target_column": "Class",
        "dtype_contract": _dtype_contract(),
        "row_hash_algorithm": ROW_HASH_ALGORITHM,
        "row_hashes": row_hashes,
        "row_hashes_sha256": row_hashes_checksum(row_hashes),
        "total_row_count": len(row_hashes),
        "fraud_count": int(frame["Class"].sum()),
        "unique_row_count": unique_row_count,
        "duplicate_row_count": len(row_hashes) - unique_row_count,
        "contains_raw_transaction_values": False,
        "sources": sources,
    }


def _canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def build_historical_quarantine_anchor_candidate(
    *,
    x_test_path: Path,
    y_test_path: Path,
) -> dict[str, Any]:
    """Derive review-only anchor evidence without trusting or writing an anchor."""
    payload = _build_historical_quarantine_payload(
        x_test_path=x_test_path,
        y_test_path=y_test_path,
    )
    if (
        payload["total_row_count"] != HISTORICAL_TEST_ROWS
        or payload["fraud_count"] != HISTORICAL_TEST_FRAUD
    ):
        raise ValueError(
            "Historical quarantine anchor candidate does not match the predeclared "
            f"retained split counts: expected {HISTORICAL_TEST_ROWS} rows and "
            f"{HISTORICAL_TEST_FRAUD} fraud rows."
        )
    sources = payload["sources"]
    return {
        "approval_required": True,
        "approval_status": "unapproved_candidate",
        "candidate_contains_row_hashes": False,
        "candidate_format_version": (
            HISTORICAL_QUARANTINE_ANCHOR_CANDIDATE_FORMAT_VERSION
        ),
        "candidate_kind": "historical_test_quarantine_anchor_candidate",
        "contains_raw_transaction_values": False,
        "decision_eligible": False,
        "dtype_contract": payload["dtype_contract"],
        "duplicate_row_count": payload["duplicate_row_count"],
        "fraud_count": payload["fraud_count"],
        "manifest_serialization": MANIFEST_SERIALIZATION,
        "manifest_sha256": hashlib.sha256(
            _canonical_manifest_bytes(payload)
        ).hexdigest(),
        "quarantine_format_version": payload["format_version"],
        "row_hash_algorithm": payload["row_hash_algorithm"],
        "row_hashes_sha256": payload["row_hashes_sha256"],
        "source_files": {
            name: {
                "filename": record["filename"],
                "size_bytes": record["size_bytes"],
            }
            for name, record in sources.items()
        },
        "source_sha256": {
            name: record["sha256"] for name, record in sources.items()
        },
        "total_row_count": payload["total_row_count"],
        "training_use_prohibited": True,
        "unique_row_count": payload["unique_row_count"],
    }


def build_historical_quarantine_manifest(
    *,
    x_test_path: Path,
    y_test_path: Path,
) -> dict[str, Any]:
    """Build a deterministic manifest only after loading an approved anchor."""
    anchor = load_historical_quarantine_anchor()
    payload = _build_historical_quarantine_payload(
        x_test_path=x_test_path,
        y_test_path=y_test_path,
    )
    _require_anchor_match(payload, anchor)
    return payload


@dataclass(frozen=True)
class _DirectoryIdentity:
    parent_fd: int | None
    name: str | None
    descriptor: int
    device: int
    inode: int


@dataclass(frozen=True)
class _OpenedOutputParent:
    descriptor: int
    final_name: str
    output_path: Path
    chain: tuple[_DirectoryIdentity, ...]


def _require_safe_directory_primitives() -> None:
    required_dir_fd = (os.open, os.mkdir, os.stat, os.link, os.unlink)
    if (
        not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or any(function not in os.supports_dir_fd for function in required_dir_fd)
        or os.stat not in os.supports_follow_symlinks
        or os.link not in os.supports_follow_symlinks
    ):
        raise RuntimeError(
            "Safe quarantine publication requires directory-descriptor and "
            "no-follow OS primitives."
        )


def _output_parts(output_path: str | Path) -> tuple[tuple[str, ...], Path]:
    raw = str(output_path)
    candidate_input = Path(raw).expanduser()
    if (
        not raw
        or candidate_input.is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or bool(PureWindowsPath(raw).drive)
        or "\\" in raw
        or any(part in {".", ".."} for part in candidate_input.parts)
    ):
        raise ValueError("Quarantine output must be a relative path inside artifacts/.")
    parts = candidate_input.parts
    if len(parts) < 2 or parts[0] != "artifacts":
        raise ValueError("Historical quarantine output must be inside ignored artifacts/.")
    if Path(parts[-1]).suffix.lower() != ".json":
        raise ValueError("Quarantine output must be a .json file.")
    root = Path(PROJECT_ROOT)
    if not root.is_absolute():
        raise RuntimeError("Canonical project root must be an absolute path.")
    return parts, root.joinpath(*parts)


def _file_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _open_directory(
    parent_fd: int | None,
    name_or_path: str | Path,
    *,
    create: bool,
) -> int:
    open_target = os.fspath(name_or_path)
    try:
        return os.open(open_target, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError:
        if not create or parent_fd is None:
            raise
        try:
            os.mkdir(open_target, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        try:
            return os.open(open_target, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        except OSError as exc:
            raise ValueError(
                "Quarantine output path contains a symbolic link or unsafe "
                f"directory: {open_target}."
            ) from exc
    except OSError as exc:
        raise ValueError(
            "Quarantine output path contains a symbolic link or unsafe "
            f"directory: {open_target}."
        ) from exc


def _verify_directory_chain(chain: tuple[_DirectoryIdentity, ...]) -> None:
    for entry in chain:
        descriptor_metadata = os.fstat(entry.descriptor)
        if not stat.S_ISDIR(descriptor_metadata.st_mode) or _file_identity(
            descriptor_metadata
        ) != (entry.device, entry.inode):
            raise ValueError("Quarantine output directory descriptor was replaced.")
        if entry.parent_fd is None:
            named_metadata = os.stat(
                PROJECT_ROOT,
                follow_symlinks=False,
            )
        else:
            if entry.name is None:
                raise RuntimeError("Invalid quarantine directory identity record.")
            named_metadata = os.stat(
                entry.name,
                dir_fd=entry.parent_fd,
                follow_symlinks=False,
            )
        if not stat.S_ISDIR(named_metadata.st_mode) or _file_identity(
            named_metadata
        ) != (entry.device, entry.inode):
            raise ValueError("Quarantine output directory path was replaced.")


def _record_directory(
    descriptor: int, *, parent_fd: int | None, name: str | None
) -> _DirectoryIdentity:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Quarantine output component is not a directory.")
    return _DirectoryIdentity(
        parent_fd=parent_fd,
        name=name,
        descriptor=descriptor,
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )


@contextmanager
def _open_output_parent(
    output_path: str | Path, *, create_parents: bool
) -> Iterator[_OpenedOutputParent | None]:
    _require_safe_directory_primitives()
    parts, candidate = _output_parts(output_path)
    descriptors: list[int] = []
    chain: list[_DirectoryIdentity] = []
    try:
        root_fd = _open_directory(None, PROJECT_ROOT, create=False)
        descriptors.append(root_fd)
        chain.append(_record_directory(root_fd, parent_fd=None, name=None))
        parent_fd = root_fd
        for part in parts[:-1]:
            try:
                child_fd = _open_directory(parent_fd, part, create=create_parents)
            except FileNotFoundError:
                yield None
                return
            descriptors.append(child_fd)
            chain.append(
                _record_directory(child_fd, parent_fd=parent_fd, name=part)
            )
            parent_fd = child_fd
        opened = _OpenedOutputParent(
            descriptor=parent_fd,
            final_name=parts[-1],
            output_path=candidate,
            chain=tuple(chain),
        )
        _verify_directory_chain(opened.chain)
        yield opened
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _reject_existing_output(parent_fd: int, final_name: str, output: Path) -> None:
    try:
        metadata = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"Quarantine output path contains a symbolic link: {output}.")
    raise FileExistsError(f"Refusing to overwrite quarantine manifest: {output}")


def resolve_quarantine_output_path(output_path: str | Path) -> Path:
    """Resolve a new relative JSON path strictly beneath ignored artifacts/."""
    _, candidate = _output_parts(output_path)
    with _open_output_parent(output_path, create_parents=False) as opened:
        if opened is not None:
            _reject_existing_output(
                opened.descriptor, opened.final_name, opened.output_path
            )
    return candidate


def _create_temporary_file(parent_fd: int, final_name: str) -> tuple[int, str]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_NOFOLLOW
    )
    for _ in range(16):
        temporary_name = f".{final_name}.{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(
                temporary_name,
                flags,
                mode=0o600,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            continue
        return descriptor, temporary_name
    raise FileExistsError("Unable to allocate a unique quarantine temporary file.")


def _publish_manifest_with_directory_fds(
    manifest: dict[str, Any], opened: _OpenedOutputParent
) -> None:
    encoded = _canonical_manifest_bytes(manifest)
    descriptor, temporary_name = _create_temporary_file(
        opened.descriptor, opened.final_name
    )
    published = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _verify_directory_chain(opened.chain)
        _reject_existing_output(
            opened.descriptor, opened.final_name, opened.output_path
        )
        try:
            os.link(
                temporary_name,
                opened.final_name,
                src_dir_fd=opened.descriptor,
                dst_dir_fd=opened.descriptor,
                follow_symlinks=False,
            )
            published = True
        except FileExistsError:
            raise FileExistsError(
                f"Refusing to overwrite quarantine manifest: {opened.output_path}"
            ) from None
        _verify_directory_chain(opened.chain)
        os.fsync(opened.descriptor)
    except BaseException:
        if published:
            os.unlink(opened.final_name, dir_fd=opened.descriptor)
        raise
    finally:
        try:
            os.unlink(temporary_name, dir_fd=opened.descriptor)
        except FileNotFoundError:
            pass


def write_historical_quarantine_manifest(
    *,
    x_test_path: Path,
    y_test_path: Path,
    output_path: str | Path,
) -> Path:
    """Atomically publish one approved hash-only quarantine manifest."""
    output = resolve_quarantine_output_path(output_path)
    manifest = build_historical_quarantine_manifest(
        x_test_path=x_test_path,
        y_test_path=y_test_path,
    )
    with _open_output_parent(output_path, create_parents=True) as opened:
        if opened is None:
            raise RuntimeError("Failed to create canonical quarantine output directory.")
        _reject_existing_output(opened.descriptor, opened.final_name, output)
        _publish_manifest_with_directory_fds(manifest, opened)
    return output


def _validate_manifest_payload(payload: dict[str, Any]) -> tuple[list[str], int]:
    required = {
        "format_version",
        "manifest_kind",
        "feature_schema",
        "target_column",
        "dtype_contract",
        "row_hash_algorithm",
        "row_hashes",
        "row_hashes_sha256",
        "total_row_count",
        "fraud_count",
        "unique_row_count",
        "duplicate_row_count",
        "contains_raw_transaction_values",
        "sources",
    }
    if set(payload) != required:
        raise ValueError("Historical quarantine manifest fields are incomplete or unexpected.")
    if (
        payload["format_version"] != HISTORICAL_QUARANTINE_FORMAT_VERSION
        or payload["manifest_kind"] != "historical_test_row_quarantine"
        or payload["feature_schema"] != list(ALL_FEATURES)
        or payload["target_column"] != "Class"
        or payload["dtype_contract"] != _dtype_contract()
        or payload["row_hash_algorithm"] != ROW_HASH_ALGORITHM
        or payload["contains_raw_transaction_values"] is not False
    ):
        raise ValueError("Historical quarantine manifest contract mismatch.")
    row_hashes = payload["row_hashes"]
    if (
        not isinstance(row_hashes, list)
        or any(
            not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value)
            for value in row_hashes
        )
        or row_hashes != sorted(row_hashes)
    ):
        raise ValueError("Historical quarantine row hashes are malformed or unsorted.")
    unique_row_count = len(set(row_hashes))
    counts = (
        payload["total_row_count"],
        payload["fraud_count"],
        payload["unique_row_count"],
        payload["duplicate_row_count"],
    )
    if (
        any(type(value) is not int for value in counts)
        or payload["total_row_count"] != len(row_hashes)
        or not 0 <= payload["fraud_count"] <= payload["total_row_count"]
        or payload["unique_row_count"] != unique_row_count
        or payload["duplicate_row_count"] != len(row_hashes) - unique_row_count
        or payload["row_hashes_sha256"] != row_hashes_checksum(row_hashes)
    ):
        raise ValueError("Historical quarantine row counts or checksum do not match.")
    sources = payload["sources"]
    if not isinstance(sources, dict) or set(sources) != {"x_test", "y_test"}:
        raise ValueError("Historical quarantine source records are incomplete.")
    for record in sources.values():
        if (
            not isinstance(record, dict)
            or set(record) != {"filename", "sha256", "size_bytes"}
            or not isinstance(record["sha256"], str)
            or not _SHA256_PATTERN.fullmatch(record["sha256"])
            or type(record["size_bytes"]) is not int
            or record["size_bytes"] <= 0
        ):
            raise ValueError("Historical quarantine source record is malformed.")
        _safe_basename(record["filename"])
    return row_hashes, unique_row_count


def load_historical_quarantine_manifest(
    manifest_path: str | Path,
) -> HistoricalTestQuarantine:
    """Load a manifest's exact bytes and verify them against the approved anchor."""
    anchor = load_historical_quarantine_anchor()
    payload, path, digest, size_bytes = _read_json_bytes(
        manifest_path, label="Historical quarantine manifest"
    )
    row_hashes, unique_row_count = _validate_manifest_payload(payload)
    _require_anchor_match(payload, anchor)
    return HistoricalTestQuarantine(
        row_hashes=frozenset(row_hashes),
        total_row_count=payload["total_row_count"],
        fraud_count=payload["fraud_count"],
        unique_row_count=unique_row_count,
        duplicate_row_count=payload["duplicate_row_count"],
        row_hashes_sha256=payload["row_hashes_sha256"],
        manifest_path=path,
        manifest_sha256=digest,
        manifest_size_bytes=size_bytes,
        anchor_path=anchor.path,
        anchor_sha256=anchor.sha256,
        anchor_size_bytes=anchor.size_bytes,
    )


def _checked_file_record(path: Path, digest: str, size_bytes: int) -> dict[str, str | int]:
    return {
        "filename": _safe_basename(path.name),
        "sha256": digest,
        "size_bytes": size_bytes,
    }


def historical_quarantine_input_records(
    quarantine: HistoricalTestQuarantine,
) -> dict[str, dict[str, str | int]]:
    """Return identities captured from the exact bytes that passed validation."""
    return {
        "historical_quarantine": _checked_file_record(
            quarantine.manifest_path,
            quarantine.manifest_sha256,
            quarantine.manifest_size_bytes,
        ),
        "historical_quarantine_anchor": _checked_file_record(
            quarantine.anchor_path,
            quarantine.anchor_sha256,
            quarantine.anchor_size_bytes,
        ),
    }


def _reverify_file(path: Path, digest: str, size_bytes: int, *, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} was replaced after verification.")
    encoded = path.read_bytes()
    if len(encoded) != size_bytes or hashlib.sha256(encoded).hexdigest() != digest:
        raise ValueError(f"{label} changed after verification.")


def reverify_historical_quarantine_identity(
    quarantine: HistoricalTestQuarantine,
) -> None:
    """Ensure checked manifest and anchor bytes remain unchanged before publication."""
    _reverify_file(
        quarantine.manifest_path,
        quarantine.manifest_sha256,
        quarantine.manifest_size_bytes,
        label="Historical quarantine manifest",
    )
    _reverify_file(
        quarantine.anchor_path,
        quarantine.anchor_sha256,
        quarantine.anchor_size_bytes,
        label="Historical quarantine anchor",
    )


def require_no_historical_test_overlap(
    frame: pd.DataFrame,
    manifest_path: str | Path,
) -> HistoricalTestQuarantine:
    """Reject decision-training data containing any locked historical test row."""
    quarantine = load_historical_quarantine_manifest(manifest_path)
    candidate_hashes = canonical_row_hashes(frame)
    overlap_count = len(set(candidate_hashes) & quarantine.row_hashes)
    if overlap_count:
        raise ValueError(
            "Decision-training data overlaps the locked historical test quarantine: "
            f"{overlap_count} unique row(s)."
        )
    return quarantine
