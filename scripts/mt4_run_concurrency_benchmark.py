"""Run the pre-registered MT4 loopback concurrency benchmark.

Serving-plumbing measurement only. Starts the API as a local subprocess bound to
127.0.0.1, drives it with a deterministic synthetic corpus, and writes
public-safe aggregate JSON. Nothing here trains, tunes, calibrates, or evaluates
a model, and no held-out role is read.

Results describe the bundle actually served. When that is a historical or demo
bundle they carry the MT4 provenance label and prove nothing about any other
bundle's quality.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.operations.benchmark import (  # noqa: E402
    CONCURRENCY_LEVELS,
    MIN_REPEATS,
    PROVENANCE_LABEL,
    BenchmarkError,
    aggregate_repeats,
    run_repeat,
    synthetic_corpus,
)
from src.operations.serving_variants import VARIANT_ENV  # noqa: E402

PREDICT_PATH = "/v1/predict"
READY_PATH = "/health/ready"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _environment_fingerprint() -> dict[str, Any]:
    import platform

    import numpy
    import sklearn
    import xgboost

    import fastapi
    import starlette
    import uvicorn

    return {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "system": f"{platform.system()} {platform.release()}",
        "cpu_count": os.cpu_count(),
        "fastapi": fastapi.__version__,
        "starlette": starlette.__version__,
        "uvicorn": uvicorn.__version__,
        "numpy": numpy.__version__,
        "scikit_learn": sklearn.__version__,
        "xgboost": xgboost.__version__,
        "workers": 1,
        "thread_env": {
            name: os.getenv(name) for name in
            ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
    }


def _wait_ready(client: Any, base: str, *, timeout_s: float) -> float:
    deadline = time.perf_counter() + timeout_s
    started = time.perf_counter()
    while time.perf_counter() < deadline:
        try:
            if client.get(f"{base}{READY_PATH}", timeout=2.0).status_code == 200:
                return (time.perf_counter() - started) * 1000.0
        except Exception:  # noqa: BLE001 - server not up yet
            pass
        time.sleep(0.05)
    raise BenchmarkError("Server did not become ready within the timeout.")


def _launch(variant: str, *, manifest: Path, artifact_root: Path, audit_log: Path,
            admission_limit: int) -> tuple[Any, str, float]:
    """Start a fresh server subprocess bound to loopback with a fresh audit log."""
    import subprocess as sp

    port = _free_port()
    env = {
        **os.environ,
        VARIANT_ENV: variant,
        "SECURESWIPE_BUNDLE_MANIFEST": str(manifest),
        "SECURESWIPE_ARTIFACT_ROOT": str(artifact_root),
        "SECURESWIPE_AUDIT_LOG": str(audit_log),
        "SECURESWIPE_MAX_CONCURRENT_PREDICTIONS": str(admission_limit),
        "PYTHONPATH": str(PROJECT_ROOT),
    }
    command = [
        sys.executable, "-m", "uvicorn",
        "--factory", "src.operations.serving_variants:create_benchmark_app",
        "--host", "127.0.0.1", "--port", str(port),
        "--workers", "1", "--log-level", "error",
    ]
    launched = time.perf_counter()
    server = sp.Popen(command, cwd=str(PROJECT_ROOT), env=env,
                      stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    return server, f"http://127.0.0.1:{port}", launched


def _shutdown(server: Any) -> None:
    server.terminate()
    try:
        server.wait(timeout=20)
    except Exception:  # noqa: BLE001 - defensive kill
        server.kill()
        server.wait(timeout=10)


def run_variant(
    variant: str,
    *,
    manifest: Path,
    artifact_root: Path,
    audit_dir: Path,
    corpus: Sequence[dict[str, float]],
    request_count: int,
    repeats: int,
    timeout_seconds: float,
    warmup_requests: int,
    admission_limit: int,
) -> dict[str, Any]:
    """Measure one serving variant across the frozen concurrency levels.

    A fresh server and a fresh audit log are used for each concurrency level, so
    audit-chain growth from earlier levels never contaminates later ones. The
    unbounded growth effect itself is measured separately.
    """
    import httpx
    import psutil

    limits = httpx.Limits(max_connections=128, max_keepalive_connections=128)
    levels: list[dict[str, Any]] = []
    cold: dict[str, Any] = {}
    resource: dict[str, Any] = {}

    for level_index, concurrency in enumerate(CONCURRENCY_LEVELS):
        audit_log = audit_dir / f"{variant}-c{concurrency}" / "audit.ndjson"
        audit_log.parent.mkdir(parents=True, exist_ok=True)
        server, base, launched = _launch(
            variant, manifest=manifest, artifact_root=artifact_root,
            audit_log=audit_log, admission_limit=admission_limit,
        )
        try:
            with httpx.Client(limits=limits) as client:
                _wait_ready(client, base, timeout_s=90.0)
                ready_ms = (time.perf_counter() - launched) * 1000.0

                if level_index == 0:
                    started = time.perf_counter()
                    first = client.post(f"{base}{PREDICT_PATH}", json=corpus[0],
                                        headers={"X-Request-ID": f"{variant}-cold"},
                                        timeout=timeout_seconds)
                    cold = {
                        "process_ready_ms": round(ready_ms, 3),
                        "first_scored_request_ms": round(
                            (time.perf_counter() - started) * 1000.0, 3),
                        "first_request_status": first.status_code,
                    }

                results = []
                for repeat in range(repeats):
                    run_repeat(client, f"{base}{PREDICT_PATH}", corpus,
                               concurrency=concurrency, request_count=warmup_requests,
                               timeout_seconds=timeout_seconds,
                               request_id_prefix=f"{variant}-w{concurrency}-{repeat}")
                    results.append(run_repeat(
                        client, f"{base}{PREDICT_PATH}", corpus,
                        concurrency=concurrency, request_count=request_count,
                        timeout_seconds=timeout_seconds,
                        request_id_prefix=f"{variant}-c{concurrency}-r{repeat}",
                    ))

                proc = psutil.Process(server.pid)
                cpu = proc.cpu_times()
                level = aggregate_repeats(results)
                level["server_cpu_user_seconds"] = round(cpu.user, 3)
                level["server_cpu_system_seconds"] = round(cpu.system, 3)
                level["server_rss_bytes"] = int(proc.memory_info().rss)
                level["audit_events_written"] = (
                    sum(1 for _ in audit_log.open()) if audit_log.exists() else 0
                )
                levels.append(level)
                resource = {
                    "last_level_cpu_user_seconds": level["server_cpu_user_seconds"],
                    "last_level_cpu_system_seconds": level["server_cpu_system_seconds"],
                    "last_level_rss_bytes": level["server_rss_bytes"],
                }
        finally:
            _shutdown(server)

    return {
        "variant": variant,
        "provenance_label": PROVENANCE_LABEL,
        "admission_limit": admission_limit,
        "fresh_server_and_audit_log_per_level": True,
        "cold_start": cold,
        "resource": resource,
        "levels": levels,
    }


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MT4 loopback concurrency benchmark.",
                                     allow_abbrev=False)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--repeats", type=int, default=MIN_REPEATS)
    parser.add_argument("--warmup-requests", type=int, default=50)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--admission-limit", type=int, default=16)
    parser.add_argument("--corpus-size", type=int, default=512)
    parser.add_argument("--variants", default="baseline,lock_free")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.repeats < MIN_REPEATS:
        raise BenchmarkError(f"The protocol requires at least {MIN_REPEATS} repeats.")

    from src.artifacts.bundle import load_model_bundle

    bundle = load_model_bundle(args.bundle_manifest, trusted_root=args.artifact_root)
    corpus = synthetic_corpus(args.corpus_size)
    args.audit_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema_version": "mt4-concurrency-benchmark-v1",
        "provenance_label": PROVENANCE_LABEL,
        "scope": "local loopback, single machine, single worker, no external network",
        "served_bundle": {
            "model_version": bundle.model_version,
            "model_artifact_sha256": bundle.model_artifact_sha256,
            "operating_threshold": bundle.operating_threshold,
            "score_type": bundle.score_type,
            "bundle_size_bytes": sum(
                p.stat().st_size for p in args.bundle_manifest.parent.rglob("*") if p.is_file()
            ),
            "is_sealed_lane_a_bundle": False,
        },
        "environment": _environment_fingerprint(),
        "corpus": {
            "size": len(corpus),
            "synthetic": True,
            "contains_real_transaction_data": False,
            "contains_labels": False,
        },
        "request_count_per_repeat": args.requests,
        "warmup_requests_per_repeat": args.warmup_requests,
        "repeats_per_level": args.repeats,
        "timeout_seconds": args.timeout_seconds,
        "concurrency_levels": list(CONCURRENCY_LEVELS),
        "variants": [],
    }
    for variant in [v.strip() for v in args.variants.split(",") if v.strip()]:
        report["variants"].append(run_variant(
            variant, manifest=args.bundle_manifest, artifact_root=args.artifact_root,
            audit_dir=args.audit_dir, corpus=corpus, request_count=args.requests,
            repeats=args.repeats, timeout_seconds=args.timeout_seconds,
            warmup_requests=args.warmup_requests, admission_limit=args.admission_limit,
        ))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"written": args.output.name,
                      "variants": [v["variant"] for v in report["variants"]]}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
