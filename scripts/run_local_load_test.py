"""Run a bounded loopback load probe and emit measured latency/error evidence."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.monitoring.io import write_report


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
        return {
            "latency_ms": latency_ms,
            "model_version": model_version,
            "ok": response.status_code == 200 and contract_valid,
            "status": response.status_code,
        }
    except httpx.HTTPError:
        return {
            "latency_ms": (time.perf_counter() - started) * 1_000,
            "model_version": None,
            "ok": False,
            "status": None,
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
) -> dict[str, Any]:
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
    started = time.perf_counter()
    with httpx.Client(timeout=timeout_seconds) as client:
        ready = client.get(f"{url.rstrip('/')}/health/ready")
        if ready.status_code != 200:
            raise RuntimeError(f"API readiness failed with HTTP {ready.status_code}.")
        warmup = _request(client, url, payload, -1)
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
    latencies = np.asarray([result["latency_ms"] for result in results], dtype=float)
    successful = sum(int(result["ok"]) for result in results)
    versions = sorted(
        {str(result["model_version"]) for result in results if result["model_version"]}
    )
    return {
        "concurrency": concurrency,
        "error_count": requests - successful,
        "error_rate": (requests - successful) / requests,
        "health_probe": {
            "latency_ms": health["latency_ms"],
            "status": health["status"],
            "timing": "concurrent_with_prediction_load",
        },
        "latency_ms": {
            "max": float(np.max(latencies)),
            "p50": float(np.quantile(latencies, 0.50)),
            "p95": float(np.quantile(latencies, 0.95)),
            "p99": float(np.quantile(latencies, 0.99)),
            "percentile_method": "numpy_linear",
        },
        "model_versions": versions,
        "request_count": requests,
        "successful_count": successful,
        "throughput_requests_per_second": requests / wall_seconds,
        "timeout_seconds": timeout_seconds,
        "runtime": {
            "httpx": importlib.metadata.version("httpx"),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
        },
        "wall_seconds": wall_seconds,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object.")
    report = run_load_test(
        url=args.url,
        payload=payload,
        requests=args.requests,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout_seconds,
    )
    write_report(report, args.output, check=False)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if report["error_count"] == 0 and report["health_probe"]["status"] == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
