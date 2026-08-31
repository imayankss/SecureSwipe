#!/usr/bin/env python3
"""Run the frozen local-only PostgreSQL V2 scale harness.

Smoke mode is deliberately non-publishable. Full mode is guarded by an
explicit confirmation flag and is intended for P1-S4b from a clean commit.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import httpx
import psycopg
import psycopg_pool
import uvicorn
from fastapi import __version__ as fastapi_version
from psycopg import sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.postgres_audit import verify_audit_chain  # noqa: E402
from api.postgres_migrations import run_migrations  # noqa: E402
from api.scale_response import BoundedPredictionRepresentation, V2_SCHEMA_VERSION  # noqa: E402
from scripts.create_synthetic_bundle import create_synthetic_bundle  # noqa: E402
from src.operations.p1_scale_benchmark import (  # noqa: E402
    CONCURRENCY_LEVELS,
    FIXTURE_VERSION,
    POSTGRES_HOST,
    POSTGRES_IMAGE,
    POSTGRES_IMAGE_DIGEST,
    POSTGRES_PORT,
    POSTGRES_VERSION,
    PREDICTION_ROUTE,
    PROTOCOL_VERSION,
    REPEAT_NUMBERS,
    STATE_BACKEND,
    WORKER_COUNTS,
    BenchmarkValidationError,
    RequestOutcome,
    RequestSpec,
    ScaleBenchmarkError,
    Workload,
    assert_safe_target,
    build_workload,
    nearest_rank,
    request_group_sha256,
    safe_api_error_evidence,
    safe_outcome_diagnostics,
    summarize_outcomes,
    validate_safe_result,
    validate_response_groups,
)
from src.operations.p1_scale_client_timing import (  # noqa: E402
    ClientRequestTimer,
    ClientTimingAggregator,
    HttpTraceRecorder,
    client_timing_enabled,
)

OWNERSHIP_PREFIX = "secureswipe-p1-s4-"
OWNERSHIP_LABEL = "secureswipe.task=p1-s4"
DATABASE_NAME = "secureswipe_p1_scale_test"
RESULT_DIRECTORY = PROJECT_ROOT / "reports" / "benchmarks" / "p1-scale-results"
TIMEOUT_SECONDS = 10.0


def _run(
    command: Sequence[str], *, timeout: float = 60.0, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _checked(command: Sequence[str], *, timeout: float = 60.0) -> str:
    result = _run(command, timeout=timeout)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise ScaleBenchmarkError(f"Command failed closed: {command[0]}: {message}")
    return result.stdout.strip()


def _git_value(*args: str) -> str:
    return _checked(("git", *args))


def _available_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _require_postgres_port_free() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        if probe.connect_ex((POSTGRES_HOST, POSTGRES_PORT)) == 0:
            raise ScaleBenchmarkError(
                "127.0.0.1:55432 is already occupied; refusing to inspect or reuse it."
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _machine_record() -> dict[str, Any]:
    memory_bytes: int | None = None
    if sys.platform == "darwin":
        value = _run(("sysctl", "-n", "hw.memsize"))
        if value.returncode == 0:
            memory_bytes = int(value.stdout.strip())
    elif Path("/proc/meminfo").exists():
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                memory_bytes = int(line.split()[1]) * 1024
                break
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "cpu": platform.processor() or platform.machine(),
        "logical_cpu_count": os.cpu_count(),
        "ram_bytes": memory_bytes,
        "python": platform.python_version(),
        "fastapi": fastapi_version,
        "uvicorn": uvicorn.__version__,
        "httpx": getattr(httpx, "__version__", "unknown"),
        "psycopg": psycopg.__version__,
        "psycopg_pool": psycopg_pool.__version__,
    }


@dataclass
class ResourceSamples:
    api_cpu_percent: list[float] = field(default_factory=list)
    api_rss_mib: list[float] = field(default_factory=list)
    postgres_cpu_percent: list[float] = field(default_factory=list)
    postgres_rss_mib: list[float] = field(default_factory=list)
    worker_cpu_percent: dict[int, list[float]] = field(default_factory=dict)
    worker_rss_mib: dict[int, list[float]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        def aggregate(values: list[float], *, rss: bool = False) -> dict[str, Any]:
            if not values:
                raise ScaleBenchmarkError("Required CPU/RSS samples were not captured.")
            return {
                "samples": len(values),
                "mean" if not rss else "median_mib": round(
                    sum(values) / len(values) if not rss else nearest_rank(values, 0.50), 3
                ),
                "peak" if not rss else "peak_mib": round(max(values), 3),
            }

        worker_ids = sorted(self.worker_cpu_percent)
        if not worker_ids:
            raise ScaleBenchmarkError("Required per-worker CPU/RSS samples were not captured.")
        workers = {
            f"worker_{index + 1}": {
                "cpu_percent": aggregate(self.worker_cpu_percent[pid]),
                "rss": aggregate(self.worker_rss_mib[pid], rss=True),
            }
            for index, pid in enumerate(worker_ids)
        }
        return {
            "sampling_interval_ms": 100,
            "api_workers": workers,
            "api_process_group_cpu_percent": aggregate(self.api_cpu_percent),
            "api_process_group_rss": aggregate(self.api_rss_mib, rss=True),
            "postgres_container_cpu_percent": aggregate(self.postgres_cpu_percent),
            "postgres_container_rss": aggregate(self.postgres_rss_mib, rss=True),
        }


class ResourceSampler:
    def __init__(self, api_pid: int, container: str, workers: int) -> None:
        self.api_pid = api_pid
        self.container = container
        self.workers = workers
        self.samples = ResourceSamples()
        self._stop = threading.Event()
        self._postgres_last_cpu_usage_seconds: float | None = None
        self._postgres_last_sample_time: float | None = None
        self._api_thread = threading.Thread(target=self._api_loop, daemon=True)
        self._postgres_thread = threading.Thread(target=self._postgres_loop, daemon=True)

    def start(self) -> None:
        self._api_thread.start()
        self._postgres_thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        self._api_thread.join(timeout=8)
        self._postgres_thread.join(timeout=8)
        return self.samples.summary()

    def _api_loop(self) -> None:
        while not self._stop.is_set():
            started = time.perf_counter()
            self._sample_api()
            self._stop.wait(max(0.0, 0.1 - (time.perf_counter() - started)))

    def _postgres_loop(self) -> None:
        while not self._stop.is_set():
            started = time.perf_counter()
            self._sample_postgres()
            self._stop.wait(max(0.0, 0.1 - (time.perf_counter() - started)))

    def _sample_api(self) -> None:
        result = _run(("ps", "-axo", "pid=,ppid=,%cpu=,rss=,command="), timeout=5)
        if result.returncode != 0:
            return
        rows: dict[int, tuple[int, float, int, str]] = {}
        for line in result.stdout.splitlines():
            fields = line.split(maxsplit=4)
            if len(fields) == 5:
                try:
                    rows[int(fields[0])] = (
                        int(fields[1]),
                        float(fields[2]),
                        int(fields[3]),
                        fields[4],
                    )
                except ValueError:
                    continue
        selected = {self.api_pid}
        changed = True
        while changed:
            changed = False
            for pid, (ppid, _, _, _) in rows.items():
                if ppid in selected and pid not in selected:
                    selected.add(pid)
                    changed = True
        observed = [rows[pid] for pid in selected if pid in rows]
        if observed:
            self.samples.api_cpu_percent.append(sum(row[1] for row in observed))
            self.samples.api_rss_mib.append(sum(row[2] for row in observed) / 1024.0)
        if self.workers == 1:
            worker_pids = [self.api_pid] if self.api_pid in rows else []
        else:
            worker_pids = sorted(
                pid
                for pid in selected
                if pid in rows
                and "multiprocessing.spawn" in rows[pid][3]
                and "resource_tracker" not in rows[pid][3]
            )[: self.workers]
        for pid in worker_pids:
            _, cpu, rss, _ = rows[pid]
            self.samples.worker_cpu_percent.setdefault(pid, []).append(cpu)
            self.samples.worker_rss_mib.setdefault(pid, []).append(rss / 1024.0)

    def _sample_postgres(self) -> None:
        result = _run(
            (
                "docker",
                "exec",
                self.container,
                "sh",
                "-c",
                "cat /sys/fs/cgroup/cpu.stat; cat /sys/fs/cgroup/memory.current",
            ),
            timeout=5,
        )
        if result.returncode != 0:
            return
        try:
            lines = result.stdout.strip().splitlines()
            usage_line = next(line for line in lines if line.startswith("usage_usec "))
            memory_bytes = int(lines[-1])
            usage_seconds = int(usage_line.split()[1]) / 1_000_000.0
            sampled_at = time.monotonic()
            self.samples.postgres_rss_mib.append(memory_bytes / (1024 * 1024))
            if (
                self._postgres_last_cpu_usage_seconds is not None
                and self._postgres_last_sample_time is not None
            ):
                elapsed = sampled_at - self._postgres_last_sample_time
                used = usage_seconds - self._postgres_last_cpu_usage_seconds
                if elapsed > 0 and used >= 0:
                    self.samples.postgres_cpu_percent.append(used / elapsed * 100.0)
            self._postgres_last_cpu_usage_seconds = usage_seconds
            self._postgres_last_sample_time = sampled_at
        except (StopIteration, ValueError):
            return


class OwnedPostgres:
    """One isolated container/volume/role, guarded so cleanup cannot broaden."""

    def __init__(self) -> None:
        token = secrets.token_hex(4)
        self.container = f"{OWNERSHIP_PREFIX}{token}"
        self.volume = f"{OWNERSHIP_PREFIX}{token}-data"
        self.role = f"p1s4_{token}"
        self.role_password = secrets.token_hex(24)
        self.schemas: set[str] = set()
        self.started = False
        self.container_created = False
        self.volume_created = False

    @property
    def owner_dsn(self) -> str:
        return f"postgresql://postgres@{POSTGRES_HOST}:{POSTGRES_PORT}/{DATABASE_NAME}"

    @property
    def app_dsn(self) -> str:
        return (
            f"postgresql://{self.role}:{self.role_password}@"
            f"{POSTGRES_HOST}:{POSTGRES_PORT}/{DATABASE_NAME}"
        )

    def __enter__(self) -> "OwnedPostgres":
        assert_safe_target(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            route=PREDICTION_ROUTE,
            backend=STATE_BACKEND,
        )
        _require_postgres_port_free()
        if shutil.which("docker") is None:
            raise ScaleBenchmarkError("Docker is required for the dedicated PostgreSQL instance.")
        local_digest = self.image_digest()
        if local_digest != POSTGRES_IMAGE_DIGEST:
            raise ScaleBenchmarkError(
                "The locally available PostgreSQL image does not match the frozen digest."
            )
        if _run(("docker", "container", "inspect", self.container)).returncode == 0:
            raise ScaleBenchmarkError("Generated task container name is unexpectedly occupied.")
        if _run(("docker", "volume", "inspect", self.volume)).returncode == 0:
            raise ScaleBenchmarkError("Generated task volume name is unexpectedly occupied.")
        _checked(("docker", "volume", "create", "--label", OWNERSHIP_LABEL, self.volume))
        self.volume_created = True
        try:
            command = (
                    "docker",
                    "run",
                    "-d",
                    "--pull",
                    "never",
                    "--name",
                    self.container,
                    "--label",
                    OWNERSHIP_LABEL,
                    "--mount",
                    f"source={self.volume},target=/var/lib/postgresql/data",
                    "-p",
                    f"{POSTGRES_HOST}:{POSTGRES_PORT}:5432",
                    "-e",
                    "POSTGRES_HOST_AUTH_METHOD=trust",
                    "-e",
                    f"POSTGRES_DB={DATABASE_NAME}",
                    "-e",
                    "POSTGRES_INITDB_ARGS=--data-checksums",
                    POSTGRES_IMAGE_DIGEST,
            )
            result = _run(command, timeout=120)
            if result.returncode != 0:
                label = _run(
                    (
                        "docker",
                        "container",
                        "inspect",
                        "--format",
                        "{{index .Config.Labels \"secureswipe.task\"}}",
                        self.container,
                    )
                )
                self.container_created = label.returncode == 0 and label.stdout.strip() == "p1-s4"
                message = (result.stderr or result.stdout).strip()
                raise ScaleBenchmarkError(f"Command failed closed: docker: {message}")
            self.container_created = True
            self.started = True
            self._wait_ready()
            version = self.server_version()
            if version != POSTGRES_VERSION:
                raise ScaleBenchmarkError(
                    f"PostgreSQL {POSTGRES_VERSION} required; dedicated instance is {version}."
                )
            self._create_application_role()
            return self
        except Exception:
            self.cleanup()
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.cleanup()

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            result = _run(
                (
                    "docker",
                    "exec",
                    self.container,
                    "psql",
                    "-At",
                    "-U",
                    "postgres",
                    "-d",
                    DATABASE_NAME,
                    "-c",
                    "SELECT 1;",
                )
            )
            if result.returncode == 0 and result.stdout.strip() == "1":
                return
            time.sleep(0.25)
        raise ScaleBenchmarkError("Dedicated PostgreSQL instance did not become ready.")

    def server_version(self) -> str:
        output = _checked(
            (
                "docker",
                "exec",
                self.container,
                "psql",
                "-At",
                "-U",
                "postgres",
                "-d",
                DATABASE_NAME,
                "-c",
                "SHOW server_version;",
            )
        )
        return output.strip()

    def _create_application_role(self) -> None:
        async def create() -> None:
            connection = await psycopg.AsyncConnection.connect(self.owner_dsn, autocommit=True)
            try:
                await connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                    ).format(sql.Identifier(self.role), sql.Literal(self.role_password))
                )
            finally:
                await connection.close()

        asyncio.run(create())

    def database_settings(self) -> dict[str, str]:
        output = _checked(
            (
                "docker",
                "exec",
                self.container,
                "psql",
                "-At",
                "-F",
                "|",
                "-U",
                "postgres",
                "-d",
                DATABASE_NAME,
                "-c",
                "SELECT name, setting FROM pg_settings WHERE name IN "
                "('data_checksums','fsync','full_page_writes','max_connections',"
                "'synchronous_commit','TimeZone') ORDER BY name;",
            )
        )
        settings = dict(line.split("|", 1) for line in output.splitlines() if "|" in line)
        required = {"data_checksums", "fsync", "full_page_writes", "max_connections", "synchronous_commit", "TimeZone"}
        if set(settings) != required:
            raise ScaleBenchmarkError("Required PostgreSQL durability settings are unavailable.")
        return settings

    def image_digest(self) -> str:
        output = _checked(
            (
                "docker",
                "image",
                "inspect",
                "--format",
                "{{index .RepoDigests 0}}",
                POSTGRES_IMAGE_DIGEST,
            )
        )
        if "@sha256:" not in output:
            raise ScaleBenchmarkError("PostgreSQL image digest is unavailable.")
        return output

    def schema_name(self, suffix: str) -> str:
        schema = f"p1s4_{self.role.removeprefix('p1s4_')}_{suffix}"[:63]
        if not schema.replace("_", "").isalnum() or not schema.startswith("p1s4_"):
            raise ScaleBenchmarkError("Unsafe task-owned schema name.")
        self.schemas.add(schema)
        return schema

    def migrate(self, schema: str) -> tuple[int, ...]:
        return asyncio.run(
            run_migrations(
                dsn=self.owner_dsn,
                schema=schema,
                apply=True,
                application_role=self.role,
            )
        )

    def drop_schema(self, schema: str) -> None:
        if schema not in self.schemas or not schema.startswith("p1s4_"):
            raise ScaleBenchmarkError("Refusing to drop a non-owned schema.")

        async def drop() -> None:
            connection = await psycopg.AsyncConnection.connect(self.owner_dsn, autocommit=True)
            try:
                await connection.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
                )
            finally:
                await connection.close()

        asyncio.run(drop())
        self.schemas.discard(schema)

    def cleanup(self) -> None:
        if not self.container.startswith(OWNERSHIP_PREFIX) or not self.volume.startswith(
            OWNERSHIP_PREFIX
        ):
            raise ScaleBenchmarkError("Refusing cleanup outside the task ownership prefix.")
        if self.container_created:
            _run(("docker", "rm", "-f", self.container), timeout=30)
            self.started = False
            self.container_created = False
        if self.volume_created:
            _run(("docker", "volume", "rm", "-f", self.volume), timeout=30)
            self.volume_created = False


class ApiCluster:
    def __init__(
        self,
        *,
        workers: int,
        postgres: OwnedPostgres,
        schema: str,
        manifest: Path,
        artifact_root: Path,
        log_path: Path,
    ) -> None:
        self.workers = workers
        self.postgres = postgres
        self.schema = schema
        self.port = _available_tcp_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        env = os.environ.copy()
        env.update(
            {
                "SECURESWIPE_STATE_BACKEND": STATE_BACKEND,
                "SECURESWIPE_POSTGRES_DSN": postgres.app_dsn,
                "SECURESWIPE_POSTGRES_SCHEMA": schema,
                "SECURESWIPE_POSTGRES_POOL_MIN_SIZE": "1",
                "SECURESWIPE_POSTGRES_POOL_MAX_SIZE": "4",
                "SECURESWIPE_POSTGRES_CONNECT_TIMEOUT_SECONDS": "2",
                "SECURESWIPE_IDEMPOTENCY_HMAC_SECRET": secrets.token_hex(32),
                "SECURESWIPE_BUNDLE_MANIFEST": str(manifest),
                "SECURESWIPE_ARTIFACT_ROOT": str(artifact_root),
                "SECURESWIPE_MAX_CONCURRENT_PREDICTIONS": "256",
                "SECURESWIPE_PREDICTION_TIMEOUT_SECONDS": "10",
                "SECURESWIPE_CORS_ORIGINS": "",
                "PYTHONPATH": str(PROJECT_ROOT),
            }
        )
        env.pop("SECURESWIPE_AUDIT_LOG", None)
        self._log = log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--workers",
                str(workers),
                "--log-level",
                "warning",
                "--no-access-log",
            ),
            cwd=PROJECT_ROOT,
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def __enter__(self) -> "ApiCluster":
        try:
            self._wait_ready()
            self._verify_worker_count()
            return self
        except Exception:
            self.stop()
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.stop()

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + 60
        last = "no response"
        with httpx.Client(timeout=1) as client:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    last = f"process exited {self.process.returncode}"
                    break
                try:
                    live = client.get(f"{self.base_url}/health/live")
                    ready = client.get(f"{self.base_url}/health/ready")
                    if live.status_code == 200 and ready.status_code == 200:
                        return
                    last = f"live={live.status_code}, ready={ready.status_code}"
                except httpx.HTTPError as exc:
                    last = type(exc).__name__
                time.sleep(0.2)
        raise ScaleBenchmarkError(f"API cluster failed readiness: {last}.")

    def _verify_worker_count(self) -> None:
        if self.workers == 1:
            if self.process.poll() is not None:
                raise ScaleBenchmarkError("Single-worker API process is not running.")
            return
        result = _run(("ps", "-axo", "pid=,ppid=,command="), timeout=5)
        rows: dict[int, tuple[int, str]] = {}
        for line in result.stdout.splitlines():
            fields = line.split(maxsplit=2)
            if len(fields) == 3:
                try:
                    rows[int(fields[0])] = (int(fields[1]), fields[2])
                except ValueError:
                    continue
        descendants = {self.process.pid}
        changed = True
        while changed:
            changed = False
            for pid, (ppid, _) in rows.items():
                if ppid in descendants and pid not in descendants:
                    descendants.add(pid)
                    changed = True
        children = [
            pid
            for pid in descendants
            if pid in rows
            and "multiprocessing.spawn" in rows[pid][1]
            and "resource_tracker" not in rows[pid][1]
        ]
        if len(children) != self.workers:
            raise ScaleBenchmarkError(
                f"Requested {self.workers} workers but process inspection found {len(children)}."
            )

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=5)
        self._log.close()


def _bounded_contract(
    response: httpx.Response,
) -> tuple[bool, dict[str, str], dict[str, Any]]:
    evidence: dict[str, Any] = {
        "server_replay": None,
        "response_sha256": None,
        "audit_receipt_sha256": None,
        "response_schema_version": None,
        "response_profile": None,
        "model_artifact_sha256": None,
        "failure_reason": None,
    }
    try:
        body = response.json()
    except (TypeError, ValueError):
        evidence["failure_reason"] = "invalid_json_response"
        return False, {}, evidence
    try:
        canonical_body = json.dumps(
            body, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError):
        evidence["failure_reason"] = "noncanonical_json_response"
        return False, {}, evidence
    evidence["response_sha256"] = hashlib.sha256(canonical_body).hexdigest()
    try:
        parsed = BoundedPredictionRepresentation.model_validate(body)
    except (TypeError, ValueError):
        evidence["failure_reason"] = "invalid_bounded_schema_or_profile"
        return False, {}, evidence
    metadata = {
            "model_version": parsed.model.model_version,
            "model_artifact_sha256": parsed.model.model_artifact_sha256,
            "bundle_format_version": parsed.model.bundle_format_version,
            "api_schema_version": parsed.schema_version,
            "response_profile": parsed.response_profile,
    }
    evidence.update(
        {
            "response_schema_version": parsed.schema_version,
            "response_profile": parsed.response_profile,
            "model_artifact_sha256": parsed.model.model_artifact_sha256,
        }
    )
    encoded = json.dumps(body, sort_keys=True).lower()
    if "score" in encoded or "request_id" in encoded:
        evidence["failure_reason"] = "score_or_request_identifier_leakage"
        return False, metadata, evidence
    receipt = response.headers.get("X-Audit-Event-Hash")
    if receipt is None:
        evidence["failure_reason"] = "missing_audit_receipt"
        return False, metadata, evidence
    if len(receipt) != 64 or any(character not in "0123456789abcdef" for character in receipt):
        evidence["failure_reason"] = "malformed_audit_receipt"
        return False, metadata, evidence
    evidence["audit_receipt_sha256"] = receipt
    replay_header = response.headers.get("X-Idempotent-Replay")
    if replay_header not in {None, "true"}:
        evidence["failure_reason"] = "invalid_replay_header"
        return False, metadata, evidence
    evidence["server_replay"] = replay_header == "true"
    return True, metadata, evidence


def _api_error_evidence(response: httpx.Response) -> dict[str, Any]:
    """Keep only the structured code, category, and header shape of a failure.

    The unbounded ``message`` field, the echoed request identifier, and the raw
    body are deliberately discarded; they are server text, not safe evidence.
    """
    try:
        body = response.json()
        parsed = True
    except (TypeError, ValueError):
        body = None
        parsed = False
    return safe_api_error_evidence(response.headers, body, parsed=parsed)


def _run_workload(base_url: str, workload: Workload) -> tuple[dict[str, Any], dict[str, str]]:
    metadata: dict[str, str] = {}
    metadata_lock = threading.Lock()
    timing = (
        ClientTimingAggregator(timeout_seconds=TIMEOUT_SECONDS)
        if client_timing_enabled()
        else None
    )

    def issue(
        spec: RequestSpec, request_timer: ClientRequestTimer | None = None
    ) -> RequestOutcome:
        group_token = request_group_sha256(spec.request_id)
        started = time.perf_counter()
        trace = HttpTraceRecorder() if request_timer is not None else None
        if request_timer is not None:
            request_timer.mark("task_started")

        def record_timing(*, request_completed: bool) -> None:
            if timing is None or request_timer is None or trace is None:
                return
            timing.record(
                request_timer.durations(),
                trace.durations(),
                connection_kind=trace.connection_kind(
                    request_completed=request_completed
                ),
            )

        try:
            if request_timer is None or trace is None:
                with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                    response = client.post(
                        f"{base_url}{PREDICTION_ROUTE}",
                        json=spec.body,
                        headers={"X-Request-ID": spec.request_id},
                    )
                latency = (time.perf_counter() - started) * 1000
            else:
                with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                    request = client.build_request(
                        "POST",
                        f"{base_url}{PREDICTION_ROUTE}",
                        json=spec.body,
                        headers={"X-Request-ID": spec.request_id},
                        extensions={"trace": trace},
                    )
                    request_timer.mark("request_started")
                    response = client.send(request, stream=True)
                    request_timer.mark("headers_received")
                    response.read()
                    request_timer.mark("body_completed")
                    response.close()
                request_timer.mark("client_completed")
                request_durations = request_timer.durations()
                latency = request_durations.get(
                    "client_e2e_ms", (time.perf_counter() - started) * 1000
                )
                record_timing(request_completed=True)
            contract_valid = True
            failure_reason: str | None = None
            evidence: dict[str, Any] = {}
            error_evidence: dict[str, Any] = {}
            if spec.kind != "malformed" and response.status_code == 200:
                contract_valid, observed, evidence = _bounded_contract(response)
                failure_reason = evidence.get("failure_reason")
                if observed:
                    with metadata_lock:
                        if metadata and metadata != observed:
                            contract_valid = False
                            failure_reason = "model_metadata_mismatch"
                        else:
                            metadata.update(observed)
            elif spec.kind == "malformed" and response.status_code == 422:
                error_evidence = _api_error_evidence(response)
                contract_valid = error_evidence["api_error_code"] == "validation_error"
                if not contract_valid:
                    failure_reason = "invalid_validation_error_contract"
            else:
                # Fail-closed statuses carry the structured code that names the
                # exact server condition; keep it instead of the status alone.
                error_evidence = _api_error_evidence(response)
                contract_valid = False
                failure_reason = "unexpected_http_status"
            return RequestOutcome(
                spec.kind,
                response.status_code,
                latency,
                contract_valid=contract_valid,
                request_group_sha256=group_token,
                server_replay=evidence.get("server_replay"),
                response_sha256=evidence.get("response_sha256"),
                audit_receipt_sha256=evidence.get("audit_receipt_sha256"),
                response_schema_version=evidence.get("response_schema_version"),
                response_profile=evidence.get("response_profile"),
                model_artifact_sha256=evidence.get("model_artifact_sha256"),
                failure_reason=failure_reason,
                api_error_code=error_evidence.get("api_error_code"),
                api_error_category=error_evidence.get("api_error_category"),
                header_classification=error_evidence.get("header_classification"),
            )
        except httpx.TimeoutException:
            if request_timer is not None:
                request_timer.mark("client_completed")
            record_timing(request_completed=False)
            return RequestOutcome(
                spec.kind,
                None,
                (time.perf_counter() - started) * 1000,
                timeout=True,
                request_group_sha256=group_token,
                failure_reason="client_timeout",
            )
        except httpx.HTTPError:
            if request_timer is not None:
                request_timer.mark("client_completed")
            record_timing(request_completed=False)
            return RequestOutcome(
                spec.kind,
                None,
                (time.perf_counter() - started) * 1000,
                transport_error=True,
                request_group_sha256=group_token,
                failure_reason="transport_error",
            )

    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workload.concurrency) as pool:
        if timing is None:
            outcomes = list(pool.map(issue, workload.requests))
        else:
            futures = [
                pool.submit(issue, spec, ClientRequestTimer.submitted_now())
                for spec in workload.requests
            ]
            outcomes = [future.result() for future in futures]
    try:
        summary = summarize_outcomes(workload, outcomes, time.perf_counter() - wall_started)
        summary["response_groups"] = validate_response_groups(outcomes)
        if timing is not None:
            client_timing = timing.snapshot()
            observed_e2e = client_timing["duration_aggregates"]["client_e2e_ms"]
            if observed_e2e["count"] != len(outcomes):
                raise ScaleBenchmarkError(
                    "Client timing did not reconcile with completed workload outcomes."
                )
            if round(observed_e2e["median_ms"], 3) != summary[
                "all_completed_latency"
            ]["p50_ms"]:
                raise ScaleBenchmarkError(
                    "Client timing E2E does not match the benchmark latency distribution."
                )
            summary["client_timing"] = client_timing
    except ScaleBenchmarkError as exc:
        raise BenchmarkValidationError(
            str(exc),
            diagnostics=safe_outcome_diagnostics(workload, outcomes, failure=str(exc)),
        ) from exc
    if not metadata:
        message = "No verified V2 response metadata was captured."
        raise BenchmarkValidationError(
            message,
            diagnostics=safe_outcome_diagnostics(workload, outcomes, failure=message),
        )
    return summary, metadata


async def _audit_state(dsn: str, schema: str) -> tuple[int, float]:
    connection = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        cursor = await connection.execute(
            sql.SQL("SELECT count(*) FROM {}.audit_events").format(sql.Identifier(schema))
        )
        row = await cursor.fetchone()
        started = time.perf_counter()
        verified = await verify_audit_chain(connection, schema=schema)
        duration = time.perf_counter() - started
        count = int(row[0]) if row else -1
        if verified.event_count != count:
            raise ScaleBenchmarkError("Audit row count and full verifier disagree.")
        return count, duration
    finally:
        await connection.close()


def _run_repeat(
    *,
    postgres: OwnedPostgres,
    workers: int,
    concurrency: int,
    repeat: int,
    smoke: bool,
    manifest: Path,
    artifact_root: Path,
    temp_root: Path,
) -> dict[str, Any]:
    phase_prefix = "smoke-" if smoke else ""
    warmup = build_workload(
        workers=workers, concurrency=concurrency, repeat=repeat, phase=f"{phase_prefix}warmup"  # type: ignore[arg-type]
    )
    measured = build_workload(
        workers=workers, concurrency=concurrency, repeat=repeat, phase=f"{phase_prefix}measured"  # type: ignore[arg-type]
    )
    schema = postgres.schema_name(f"w{workers}_c{concurrency}_r{repeat}")
    migrations = postgres.migrate(schema)
    try:
        try:
            with ApiCluster(
                workers=workers,
                postgres=postgres,
                schema=schema,
                manifest=manifest,
                artifact_root=artifact_root,
                log_path=temp_root / f"api-w{workers}-c{concurrency}-r{repeat}.log",
            ) as cluster:
                sampler = ResourceSampler(cluster.process.pid, postgres.container, workers)
                sampler.start()
                try:
                    before, _ = asyncio.run(_audit_state(postgres.app_dsn, schema))
                    warmup_result, warmup_metadata = _run_workload(cluster.base_url, warmup)
                    after_warmup, _ = asyncio.run(_audit_state(postgres.app_dsn, schema))
                    measured_result, measured_metadata = _run_workload(cluster.base_url, measured)
                    after_measured, verifier_seconds = asyncio.run(
                        _audit_state(postgres.app_dsn, schema)
                    )
                finally:
                    resources = sampler.stop()
        except BenchmarkValidationError as exc:
            try:
                event_count, verifier_seconds = asyncio.run(
                    _audit_state(postgres.app_dsn, schema)
                )
                audit_diagnostic: dict[str, Any] = {
                    "event_count": event_count,
                    "full_chain_verifier": "verified",
                    "full_chain_verifier_seconds": round(verifier_seconds, 6),
                }
            except Exception as audit_exc:
                audit_diagnostic = {
                    "event_count": None,
                    "full_chain_verifier": "failed",
                    "failure_type": type(audit_exc).__name__,
                }
            exc.diagnostics.update(
                {
                    "workers": workers,
                    "concurrency": concurrency,
                    "repeat": repeat,
                    "audit": audit_diagnostic,
                    "temporary_api_log_policy": "removed_after_safe_diagnostic_capture",
                }
            )
            raise
        expected_warmup_growth = warmup.counts["valid"]
        expected_measured_growth = measured.counts["valid"]
        if after_warmup - before != expected_warmup_growth:
            raise ScaleBenchmarkError("Warm-up audit-event growth did not reconcile.")
        if after_measured - after_warmup != expected_measured_growth:
            raise ScaleBenchmarkError("Measured audit-event growth did not reconcile.")
        if warmup_metadata != measured_metadata:
            raise ScaleBenchmarkError("V2 model metadata changed within one repeat.")
        return {
            "workers": workers,
            "concurrency": concurrency,
            "repeat": repeat,
            "migrations_applied": list(migrations),
            "warmup": {"manifest": warmup.safe_manifest(), "result": warmup_result},
            "measured": {"manifest": measured.safe_manifest(), "result": measured_result},
            "model": measured_metadata,
            "audit": {
                "before": before,
                "after_warmup": after_warmup,
                "after_measured": after_measured,
                "warmup_growth": after_warmup - before,
                "measured_growth": after_measured - after_warmup,
                "full_verifier_seconds": round(verifier_seconds, 6),
                "full_verifier_status": "verified",
            },
            "resources": resources,
        }
    finally:
        postgres.drop_schema(schema)


def _run_audit_growth(
    *, postgres: OwnedPostgres, manifest: Path, artifact_root: Path, temp_root: Path
) -> dict[str, Any]:
    """Run the frozen 10k sequential growth procedure for full mode only."""
    from src.operations.benchmark import synthetic_corpus

    schema = postgres.schema_name("audit_growth")
    postgres.migrate(schema)
    latencies: list[float] = []
    checkpoints: dict[str, Any] = {}
    corpus = synthetic_corpus(700, seed=42)
    try:
        with ApiCluster(
            workers=1,
            postgres=postgres,
            schema=schema,
            manifest=manifest,
            artifact_root=artifact_root,
            log_path=temp_root / "api-audit-growth.log",
        ) as cluster:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                for index in range(1, 10_001):
                    started = time.perf_counter()
                    response = client.post(
                        f"{cluster.base_url}{PREDICTION_ROUTE}",
                        json=corpus[(index - 1) % len(corpus)],
                        headers={"X-Request-ID": f"p1sf-v1-audit-growth-{index:05d}"},
                    )
                    latencies.append((time.perf_counter() - started) * 1000)
                    valid, _, evidence = _bounded_contract(response)
                    if (
                        response.status_code != 200
                        or not valid
                        or evidence["server_replay"] is not False
                    ):
                        raise ScaleBenchmarkError(f"Audit-growth request {index} failed closed.")
                    if index in {100, 1_000, 10_000}:
                        count, verifier_seconds = asyncio.run(
                            _audit_state(postgres.app_dsn, schema)
                        )
                        if count != index:
                            raise ScaleBenchmarkError("Audit-growth event count did not reconcile.")
                        window = latencies[-10:]
                        checkpoints[str(index)] = {
                            "window": f"{index - 9}..{index}",
                            "append_median_ms": round(nearest_rank(window, 0.50), 3),
                            "append_p99_ms": round(nearest_rank(window, 0.99), 3),
                            "full_verifier_seconds": round(verifier_seconds, 6),
                            "full_verifier_status": "verified",
                        }
        return {"events": 10_000, "checkpoints": checkpoints}
    finally:
        postgres.drop_schema(schema)


CSV_FIELDNAMES = (
    "workers",
    "concurrency",
    "repeat",
    "phase",
    "attempted",
    "successful_2xx",
    "expected_422",
    "unexpected_non_2xx",
    "timeouts",
    "transport_errors",
    "wall_seconds",
    "successful_rps",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "api_cpu_percent_mean",
    "api_rss_median_mib",
    "audit_growth",
)


def _repeat_csv_rows(runs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for repeat in runs:
        resources = repeat.get("resources", {})
        for phase in ("warmup", "measured"):
            summary = repeat[phase]["result"]
            rows.append(
                {
                    "workers": repeat["workers"],
                    "concurrency": repeat["concurrency"],
                    "repeat": repeat["repeat"],
                    "phase": phase,
                    "attempted": summary["attempted"],
                    "successful_2xx": summary["successful_2xx"],
                    "expected_422": summary["expected_non_2xx"],
                    "unexpected_non_2xx": summary["unexpected_non_2xx"],
                    "timeouts": summary["timeouts"],
                    "transport_errors": summary["transport_errors"],
                    "wall_seconds": summary["wall_seconds"],
                    "successful_rps": summary["successful_rps"],
                    "p50_ms": summary["all_completed_latency"]["p50_ms"],
                    "p95_ms": summary["all_completed_latency"]["p95_ms"],
                    "p99_ms": summary["all_completed_latency"]["p99_ms"],
                    "api_cpu_percent_mean": resources.get(
                        "api_process_group_cpu_percent", {}
                    ).get("mean"),
                    "api_rss_median_mib": resources.get("api_process_group_rss", {}).get(
                        "median_mib"
                    ),
                    "audit_growth": repeat["audit"][f"{phase}_growth"],
                }
            )
    return rows


def _write_repeat_csv(runs: Sequence[dict[str, Any]], path: Path) -> Path:
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_FIELDNAMES))
        writer.writeheader()
        writer.writerows(_repeat_csv_rows(runs))
    os.replace(temporary, path)
    return path


def _write_safe_json(document: dict[str, Any], path: Path) -> Path:
    """Validate, then replace atomically so a later crash cannot truncate it."""
    validate_safe_result(document)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)
    return path


class IncrementalEvidenceLog:
    """Persist privacy-safe evidence after every completed repeat.

    A benchmark cell that fails closed must not discard the cells that already
    finished, so the log is rewritten atomically as each repeat completes and is
    finalized on both the success and the failure path.
    """

    def __init__(self, *, run_id: str, output_dir: Path, header: dict[str, Any]) -> None:
        self.run_id = run_id
        self.output_dir = output_dir
        self.header = dict(header)
        self.runs: list[dict[str, Any]] = []
        self.json_path = output_dir / f"{run_id}-progress.json"
        self.csv_path = output_dir / f"{run_id}-progress.csv"
        output_dir.mkdir(parents=True, exist_ok=True)
        self._flush(status="started")

    def snapshot(
        self, *, status: str, failure: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            **self.header,
            "run_id": self.run_id,
            "diagnostic_kind": "p1_scale_incremental_evidence",
            "evidence_status": status,
            "publishable": False,
            "completed_repeat_count": len(self.runs),
            "completed_runs": self.runs,
        }
        if failure is not None:
            document["failure"] = failure
        return document

    def _flush(
        self, *, status: str, failure: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        document = self.snapshot(status=status, failure=failure)
        _write_safe_json(document, self.json_path)
        _write_repeat_csv(self.runs, self.csv_path)
        return document

    def record_repeat(self, record: dict[str, Any]) -> dict[str, Any]:
        validate_safe_result(record)
        self.runs.append(record)
        return self._flush(status="in_progress")

    def record_failure(self, failure: dict[str, Any]) -> dict[str, Any]:
        return self._flush(status="failed_after_completed_repeats", failure=failure)

    def record_completion(self) -> dict[str, Any]:
        return self._flush(status="completed")

    def relative_paths(self) -> list[str]:
        paths = []
        for path in (self.json_path, self.csv_path):
            try:
                paths.append(str(path.relative_to(PROJECT_ROOT)))
            except ValueError:
                paths.append(str(path))
        return paths


def _write_results(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    token = report["run_id"]
    json_path = _write_safe_json(report, output_dir / f"{token}.json")
    csv_path = _write_repeat_csv(report["runs"], output_dir / f"{token}.csv")
    return json_path, csv_path


def _write_partial_diagnostic(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return _write_safe_json(report, output_dir / f"{report['run_id']}-partial.json")


def run_harness(*, mode: str, output_dir: Path, confirm_full_matrix: bool) -> dict[str, Any]:
    if mode == "full" and not confirm_full_matrix:
        raise ScaleBenchmarkError("Full mode requires --confirm-full-matrix.")
    if mode == "full":
        if _run(("git", "diff", "--quiet")).returncode != 0 or _run(
            ("git", "diff", "--cached", "--quiet")
        ).returncode != 0:
            raise ScaleBenchmarkError("Full results require a clean tracked working tree.")
    run_id = f"p1-scale-{'smoke' if mode == 'smoke' else 'full'}-{int(time.time())}"
    commit_sha = _git_value("rev-parse", "HEAD")
    with tempfile.TemporaryDirectory(prefix="secureswipe-p1-s4-") as temporary:
        # macOS exposes /var as a symlink to /private/var. The bundle publisher
        # intentionally rejects symlinked publication parents, so canonicalize
        # this task-owned temporary root before creating the synthetic bundle.
        temp_root = Path(temporary).resolve(strict=True)
        artifact_root = temp_root / "synthetic-bundle"
        manifest = create_synthetic_bundle(artifact_root)
        bundle_manifest_sha256 = _sha256_file(manifest)
        with OwnedPostgres() as postgres:
            evidence_header = {
                "diagnostic_kind": "p1_scale_incremental_evidence",
                "mode": mode,
                "protocol_version": PROTOCOL_VERSION,
                "fixture_version": FIXTURE_VERSION,
                "source_commit_sha": commit_sha,
                "bundle_manifest_sha256": bundle_manifest_sha256,
                "artifact_classification": "synthetic_reference_only_no_lane_a_claim",
                "runtime": _machine_record(),
                "postgresql": {
                    "version": postgres.server_version(),
                    "image": POSTGRES_IMAGE,
                    "image_digest": postgres.image_digest(),
                },
            }
            evidence = IncrementalEvidenceLog(
                run_id=run_id, output_dir=output_dir, header=evidence_header
            )
            runs = evidence.runs
            dimensions = (
                [(1, 1, 1)]
                if mode == "smoke"
                else [
                    (workers, concurrency, repeat)
                    for workers in WORKER_COUNTS
                    for concurrency in CONCURRENCY_LEVELS
                    for repeat in REPEAT_NUMBERS
                ]
            )
            try:
                for workers, concurrency, repeat in dimensions:
                    evidence.record_repeat(
                        _run_repeat(
                            postgres=postgres,
                            workers=workers,
                            concurrency=concurrency,
                            repeat=repeat,
                            smoke=mode == "smoke",
                            manifest=manifest,
                            artifact_root=artifact_root,
                            temp_root=temp_root,
                        )
                    )
            except BenchmarkValidationError as exc:
                evidence.record_failure(exc.diagnostics)
                diagnostic = {
                    **evidence_header,
                    "run_id": run_id,
                    "diagnostic_kind": "p1_scale_partial_failure",
                    "publishable": False,
                    "completed_repeat_count": len(runs),
                    "completed_runs": runs,
                    "incremental_evidence_files": evidence.relative_paths(),
                    "failure": exc.diagnostics,
                }
                path = _write_partial_diagnostic(diagnostic, output_dir)
                relative = path.relative_to(PROJECT_ROOT)
                raise ScaleBenchmarkError(
                    f"{exc} Privacy-safe partial diagnostic: {relative}."
                ) from exc
            audit_growth = (
                {"status": "not_run_in_non_publishable_smoke"}
                if mode == "smoke"
                else _run_audit_growth(
                    postgres=postgres,
                    manifest=manifest,
                    artifact_root=artifact_root,
                    temp_root=temp_root,
                )
            )
            report: dict[str, Any] = {
                "run_id": run_id,
                "mode": mode,
                "publishable": False if mode == "smoke" else True,
                "protocol_version": PROTOCOL_VERSION,
                "fixture_version": FIXTURE_VERSION,
                "source_commit_sha": commit_sha,
                "tracked_tree_clean": _run(("git", "diff", "--quiet")).returncode == 0
                and _run(("git", "diff", "--cached", "--quiet")).returncode == 0,
                "api": {
                    "schema_version": V2_SCHEMA_VERSION,
                    "state_backend": STATE_BACKEND,
                    "prediction_route": PREDICTION_ROUTE,
                },
                "bundle_manifest_sha256": bundle_manifest_sha256,
                "artifact_classification": "synthetic_reference_only_no_lane_a_claim",
                "environment": {
                    **_machine_record(),
                    "postgresql_version": postgres.server_version(),
                    "postgresql_image": POSTGRES_IMAGE,
                    "postgresql_image_digest": postgres.image_digest(),
                    "postgresql_host": POSTGRES_HOST,
                    "postgresql_port": POSTGRES_PORT,
                    "postgresql_settings": postgres.database_settings(),
                },
                "frozen_matrix": {
                    "workers": list(WORKER_COUNTS),
                    "concurrency": list(CONCURRENCY_LEVELS),
                    "repeats": list(REPEAT_NUMBERS),
                    "warmup_counts": {"valid": 70, "replay": 20, "malformed": 10},
                    "measured_counts": {"valid": 700, "replay": 200, "malformed": 100},
                    "audit_growth_checkpoints": [100, 1_000, 10_000],
                },
                "runs": runs,
                "audit_growth": audit_growth,
            }
            evidence.record_completion()
            paths = _write_results(report, output_dir)
            report["result_files"] = [str(path.relative_to(PROJECT_ROOT)) for path in paths]
            report["incremental_evidence_files"] = evidence.relative_paths()
            return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--output-dir", type=Path, default=RESULT_DIRECTORY)
    parser.add_argument("--confirm-full-matrix", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_harness(
            mode=args.mode,
            output_dir=args.output_dir.resolve(),
            confirm_full_matrix=args.confirm_full_matrix,
        )
    except (ScaleBenchmarkError, OSError, psycopg.Error, subprocess.SubprocessError) as exc:
        print(f"P1 scale harness failed closed: {exc}", file=sys.stderr)
        return 1
    smoke = report["runs"][0] if report["mode"] == "smoke" else None
    print(
        json.dumps(
            {
                "mode": report["mode"],
                "publishable": report["publishable"],
                "run_id": report["run_id"],
                "result_files": report["result_files"],
                "incremental_evidence_files": report["incremental_evidence_files"],
                "smoke_warmup": smoke["warmup"]["result"] if smoke else None,
                "smoke_measured": smoke["measured"]["result"] if smoke else None,
                "audit": smoke["audit"] if smoke else None,
                "cleanup": "task-owned resources released on context exit",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
