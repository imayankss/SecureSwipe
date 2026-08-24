"""Run a bounded loopback load probe and emit measured latency/error evidence."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlparse

import httpx
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.monitoring.io import write_report


def compute_latency_percentiles(latencies_ms: Sequence[float]) -> dict[str, float | str]:
    """Pure percentile computation, isolated so it is unit-testable without HTTP.

    Uses numpy's default (linear) interpolation, matching the historical
    "numpy_linear" method label. Raises on empty or non-finite input instead
    of silently producing NaN/undefined percentiles.
    """
    if not latencies_ms:
        raise ValueError("latencies_ms must not be empty.")
    array = np.asarray(latencies_ms, dtype=float)
    if not np.all(np.isfinite(array)):
        raise ValueError("latencies_ms must contain only finite values.")
    return {
        "max": float(np.max(array)),
        "p50": float(np.quantile(array, 0.50)),
        "p95": float(np.quantile(array, 0.95)),
        "p99": float(np.quantile(array, 0.99)),
        "percentile_method": "numpy_linear",
    }


def _read_total_memory_bytes() -> int | None:
    """Best-effort, dependency-free total system RAM. None if not determinable."""
    try:
        if platform.system() == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
            return None
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            )
            return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def _sample_rss_kib(pid: int) -> int | None:
    """Best-effort RSS sample for an operator-supplied server PID via `ps`."""
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class _PeakMemorySampler:
    """Polls RSS for an operator-supplied PID in a background thread.

    Best effort only: if `ps` is unavailable or the PID is inaccessible
    (different container/namespace, no permission), peak() returns None
    rather than raising, so a missing sample never fails the load run.
    """

    def __init__(self, pid: int, interval_seconds: float = 0.05) -> None:
        self._pid = pid
        self._interval = interval_seconds
        self._peak_kib: int | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "_PeakMemorySampler":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            sample = _sample_rss_kib(self._pid)
            if sample is not None:
                self._peak_kib = sample if self._peak_kib is None else max(self._peak_kib, sample)
            self._stop.wait(self._interval)

    def stop(self) -> int | None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        return self._peak_kib


def _bundle_directory_size_bytes(manifest_path: Path | None) -> int | None:
    """Local file-size evidence only; never deserializes or trusts the bundle."""
    if manifest_path is None:
        return None
    try:
        directory = manifest_path.expanduser().resolve().parent
        return sum(entry.stat().st_size for entry in directory.rglob("*") if entry.is_file())
    except OSError:
        return None


def _request(
    client: httpx.Client,
    url: str,
    payload: dict[str, float],
    request_number: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.post(
            f"{url.rstrip('/')}/v1/predict",
            json=payload,
            headers={"X-Request-ID": f"local-load-{request_number}"},
        )
    except httpx.TimeoutException:
        return {
            "latency_ms": (time.perf_counter() - started) * 1_000,
            "model_version": None,
            "ok": False,
            "status": None,
            "error_kind": "timeout",
        }
    except httpx.HTTPError:
        return {
            "latency_ms": (time.perf_counter() - started) * 1_000,
            "model_version": None,
            "ok": False,
            "status": None,
            "error_kind": "transport_error",
        }
    latency_ms = (time.perf_counter() - started) * 1_000
    body = response.json() if response.status_code == 200 else {}
    model_version = body.get("model_version")
    contract_valid = (
        isinstance(model_version, str)
        and model_version != ""
        and body.get("schema_version") == "1.0"
        and body.get("decision") in {"review", "pass"}
        and isinstance(body.get("decision_score"), (int, float))
        and 0.0 <= float(body["decision_score"]) <= 1.0
    )
    ok = response.status_code == 200 and contract_valid
    return {
        "latency_ms": latency_ms,
        "model_version": model_version,
        "ok": ok,
        "status": response.status_code,
        "error_kind": None if ok else "non_2xx",
    }


def _health_probe(client: httpx.Client, url: str) -> dict[str, float | int | None]:
    started = time.perf_counter()
    try:
        response = client.get(f"{url.rstrip('/')}/health/live")
        return {
            "latency_ms": (time.perf_counter() - started) * 1_000,
            "status": response.status_code,
        }
    except httpx.HTTPError:
        return {
            "latency_ms": (time.perf_counter() - started) * 1_000,
            "status": None,
        }


def run_load_test(
    *,
    url: str,
    payload: dict[str, float],
    requests: int,
    concurrency: int,
    timeout_seconds: float,
    commit_sha: str | None = None,
    bundle_manifest: Path | None = None,
    server_pid: int | None = None,
    server_start_epoch: float | None = None,
) -> dict[str, Any]:
    if server_pid is not None and server_pid < 1:
        raise ValueError("server_pid must be a positive integer when supplied.")
    if server_start_epoch is not None and server_start_epoch > time.time():
        raise ValueError("server_start_epoch must not be in the future.")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("url must target a loopback HTTP(S) address.")
    if not 1 <= requests <= 10_000:
        raise ValueError("requests must be from 1 to 10000.")
    if not 1 <= concurrency <= min(100, requests):
        raise ValueError("concurrency must be from 1 to min(100, requests).")
    if not math.isfinite(timeout_seconds) or not 0.1 <= timeout_seconds <= 60.0:
        raise ValueError("timeout_seconds must be finite and from 0.1 to 60.")
    sampler = _PeakMemorySampler(server_pid).start() if server_pid is not None else None
    started = time.perf_counter()
    with httpx.Client(timeout=timeout_seconds) as client:
        ready = client.get(f"{url.rstrip('/')}/health/ready")
        if ready.status_code != 200:
            raise RuntimeError(f"API readiness failed with HTTP {ready.status_code}.")
        model_info_response = client.get(f"{url.rstrip('/')}/v1/model-info")
        if model_info_response.status_code != 200:
            raise RuntimeError(
                f"Model-info probe failed with HTTP {model_info_response.status_code}."
            )
        model_info_body = model_info_response.json()
        bundle_fingerprint = {
            "model_version": model_info_body.get("model_version"),
            "bundle_format_version": model_info_body.get("bundle_format_version"),
            "training_data_fingerprint": model_info_body.get("training_data_fingerprint"),
        }
        warmup_completed_epoch = None
        warmup = _request(client, url, payload, -1)
        warmup_completed_epoch = time.time()
        if not warmup["ok"]:
            raise RuntimeError("Synthetic warmup prediction failed.")
        with ThreadPoolExecutor(max_workers=concurrency + 1) as executor:
            first_wave = [
                executor.submit(_request, client, url, payload, index)
                for index in range(min(concurrency, requests))
            ]
            health_future = executor.submit(_health_probe, client, url)
            remaining = [
                executor.submit(_request, client, url, payload, index)
                for index in range(concurrency, requests)
            ]
            futures = first_wave + remaining
            results = [future.result() for future in as_completed(futures)]
            health = health_future.result()
    wall_seconds = time.perf_counter() - started
    peak_memory_kib = sampler.stop() if sampler is not None else None
    latencies = [result["latency_ms"] for result in results]
    successful = sum(int(result["ok"]) for result in results)
    timeout_count = sum(1 for result in results if result.get("error_kind") == "timeout")
    transport_error_count = sum(
        1 for result in results if result.get("error_kind") == "transport_error"
    )
    non_2xx_count = sum(1 for result in results if result.get("error_kind") == "non_2xx")
    versions = sorted(
        {str(result["model_version"]) for result in results if result["model_version"]}
    )
    cold_start_seconds = (
        warmup_completed_epoch - server_start_epoch
        if server_start_epoch is not None and warmup_completed_epoch is not None
        else None
    )
    return {
        "endpoint": "/v1/predict",
        "payload_mix": "single_fixed_payload",
        "commit_sha": commit_sha,
        "bundle_fingerprint": bundle_fingerprint,
        "bundle_size_bytes": _bundle_directory_size_bytes(bundle_manifest),
        "concurrency": concurrency,
        "error_count": requests - successful,
        "error_rate": (requests - successful) / requests,
        "error_breakdown": {
            "non_2xx_count": non_2xx_count,
            "timeout_count": timeout_count,
            "transport_error_count": transport_error_count,
        },
        "health_probe": {
            "latency_ms": health["latency_ms"],
            "status": health["status"],
            "timing": "concurrent_with_prediction_load",
        },
        "warm_up": {
            "latency_ms": warmup["latency_ms"],
            "status": warmup["status"],
        },
        "cold_start_seconds": cold_start_seconds,
        "cold_start_note": (
            "measured server_start_epoch to warm-up completion"
            if cold_start_seconds is not None
            else "not measured: requires operator-supplied --server-start-epoch"
        ),
        "peak_memory_kib": peak_memory_kib,
        "peak_memory_note": (
            "sampled via `ps -o rss=` on the supplied --server-pid every 50ms"
            if server_pid is not None
            else "not measured: requires operator-supplied --server-pid"
        ),
        "latency_ms": compute_latency_percentiles(latencies),
        "model_versions": versions,
        "request_count": requests,
        "successful_count": successful,
        "throughput_requests_per_second": requests / wall_seconds,
        "successful_throughput_requests_per_second": successful / wall_seconds,
        "timeout_seconds": timeout_seconds,
        "environment": {
            "cpu_count": os.cpu_count(),
            "total_memory_bytes": _read_total_memory_bytes(),
        },
        "runtime": {
            "httpx": importlib.metadata.version("httpx"),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        },
        "wall_seconds": wall_seconds,
    }


@dataclass(frozen=True)
class RampStopCriteria:
    """Bounds that halt a progressive concurrency ramp before it goes further."""

    max_error_rate: float = 0.01
    max_p95_latency_ms: float = 500.0
    required_health_probe_status: int = 200


def run_progressive_load_test(
    *,
    url: str,
    payload: dict[str, float],
    concurrency_levels: Sequence[int],
    requests_per_stage: int,
    timeout_seconds: float,
    stop_criteria: RampStopCriteria = RampStopCriteria(),
    stage_runner: Callable[..., dict[str, Any]] = run_load_test,
) -> dict[str, Any]:
    """Increase concurrency stage by stage, stopping at the first stage that
    exceeds configurable correctness/latency/availability bounds.

    `stage_runner` defaults to `run_load_test` but is injectable so tests can
    supply canned per-stage results instead of making real HTTP calls.
    """
    if not concurrency_levels:
        raise ValueError("concurrency_levels must not be empty.")
    levels = list(concurrency_levels)
    if levels != sorted(levels) or len(set(levels)) != len(levels):
        raise ValueError("concurrency_levels must be strictly ascending with no repeats.")
    if not 1 <= requests_per_stage <= 10_000:
        raise ValueError("requests_per_stage must be from 1 to 10000.")

    stages: list[dict[str, Any]] = []
    stopped_reason: str | None = None
    stopped_at_concurrency: int | None = None
    for level in levels:
        stage = stage_runner(
            url=url,
            payload=payload,
            requests=requests_per_stage,
            concurrency=level,
            timeout_seconds=timeout_seconds,
        )
        stages.append(stage)
        if stage["error_rate"] > stop_criteria.max_error_rate:
            stopped_reason = "error_rate_exceeded"
        elif stage["latency_ms"]["p95"] > stop_criteria.max_p95_latency_ms:
            stopped_reason = "p95_latency_exceeded"
        elif stage["health_probe"]["status"] != stop_criteria.required_health_probe_status:
            stopped_reason = "health_probe_degraded"
        if stopped_reason is not None:
            stopped_at_concurrency = level
            break
    return {
        "stages": stages,
        "concurrency_levels_requested": levels,
        "stopped_reason": stopped_reason,
        "stopped_at_concurrency": stopped_at_concurrency,
        "completed_all_levels": stopped_reason is None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--commit-sha",
        default=None,
        help="Operator-supplied VCS ref (e.g. $(git rev-parse HEAD)); recorded, not derived.",
    )
    parser.add_argument(
        "--bundle-manifest",
        type=Path,
        default=None,
        help="Local manifest path used only to record bundle_size_bytes evidence.",
    )
    parser.add_argument(
        "--server-pid",
        type=int,
        default=None,
        help="PID of the running API server, sampled via `ps` for peak_memory_kib.",
    )
    parser.add_argument(
        "--server-start-epoch",
        type=float,
        default=None,
        help="Unix timestamp the server process was started, for cold_start_seconds.",
    )
    parser.add_argument(
        "--ramp",
        action="store_true",
        help="Progressively increase concurrency and stop at configured bounds.",
    )
    parser.add_argument(
        "--ramp-concurrency-levels",
        default="1,2,4,8",
        help="Comma-separated, strictly ascending concurrency levels for --ramp.",
    )
    parser.add_argument("--ramp-requests-per-stage", type=int, default=50)
    parser.add_argument("--ramp-max-error-rate", type=float, default=0.01)
    parser.add_argument("--ramp-max-p95-latency-ms", type=float, default=500.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object.")
    if args.ramp:
        levels = [int(item.strip()) for item in args.ramp_concurrency_levels.split(",")]
        report = run_progressive_load_test(
            url=args.url,
            payload=payload,
            concurrency_levels=levels,
            requests_per_stage=args.ramp_requests_per_stage,
            timeout_seconds=args.timeout_seconds,
            stop_criteria=RampStopCriteria(
                max_error_rate=args.ramp_max_error_rate,
                max_p95_latency_ms=args.ramp_max_p95_latency_ms,
            ),
        )
        write_report(report, args.output, check=False)
        print(json.dumps(report, sort_keys=True, allow_nan=False))
        return 0 if report["completed_all_levels"] else 1
    report = run_load_test(
        url=args.url,
        payload=payload,
        requests=args.requests,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout_seconds,
        commit_sha=args.commit_sha,
        bundle_manifest=args.bundle_manifest,
        server_pid=args.server_pid,
        server_start_epoch=args.server_start_epoch,
    )
    write_report(report, args.output, check=False)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if report["error_count"] == 0 and report["health_probe"]["status"] == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
