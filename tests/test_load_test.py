"""Bounded local load-harness validation tests."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from scripts.run_local_load_test import (
    RampStopCriteria,
    _bundle_directory_size_bytes,
    _bundle_local_identity,
    compute_latency_percentiles,
    run_load_test,
    run_progressive_load_test,
)


@pytest.mark.parametrize(
    "requests,concurrency,timeout",
    [(0, 1, 1.0), (10_001, 1, 1.0), (10, 0, 1.0), (2, 3, 1.0), (1, 1, 0.0)],
)
def test_load_harness_rejects_unbounded_parameters(
    requests: int, concurrency: int, timeout: float
) -> None:
    with pytest.raises(ValueError):
        run_load_test(
            url="http://127.0.0.1:1",
            payload={},
            requests=requests,
            concurrency=concurrency,
            timeout_seconds=timeout,
        )


@pytest.mark.parametrize("url", ["https://example.com", "http://192.0.2.1:8000", "file:///tmp/x"])
def test_load_harness_refuses_non_loopback_targets(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        run_load_test(
            url=url,
            payload={},
            requests=1,
            concurrency=1,
            timeout_seconds=1.0,
        )


def test_load_harness_rejects_invalid_server_pid() -> None:
    with pytest.raises(ValueError, match="server_pid"):
        run_load_test(
            url="http://127.0.0.1:1",
            payload={},
            requests=1,
            concurrency=1,
            timeout_seconds=1.0,
            server_pid=0,
        )


def test_load_harness_rejects_future_server_start_epoch() -> None:
    with pytest.raises(ValueError, match="server_start_epoch"):
        run_load_test(
            url="http://127.0.0.1:1",
            payload={},
            requests=1,
            concurrency=1,
            timeout_seconds=1.0,
            server_start_epoch=32_503_680_000.0,  # year 3000, unambiguously future
        )


@pytest.mark.parametrize(
    ("latencies_ms", "expected"),
    [
        (
            [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
            {
                "max": 100.0,
                "p50": 55.0,
                "p95": 95.49999999999999,
                "p99": 99.1,
                "percentile_method": "numpy_linear",
            },
        ),
        (
            [1.0, 2.0, 3.0, 4.0],
            {
                "max": 4.0,
                "p50": 2.5,
                "p95": 3.8499999999999996,
                "p99": 3.9699999999999998,
                "percentile_method": "numpy_linear",
            },
        ),
    ],
)
def test_compute_latency_percentiles_matches_known_values(
    latencies_ms: list[float], expected: dict[str, float | str]
) -> None:
    assert compute_latency_percentiles(latencies_ms) == expected


def test_compute_latency_percentiles_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        compute_latency_percentiles([])


def test_compute_latency_percentiles_rejects_non_finite_input() -> None:
    with pytest.raises(ValueError, match="finite"):
        compute_latency_percentiles([1.0, float("nan"), 3.0])


def test_bundle_directory_size_bytes_is_none_without_a_manifest() -> None:
    assert _bundle_directory_size_bytes(None) is None


def test_bundle_directory_size_bytes_sums_files_in_manifest_directory(tmp_path) -> None:
    bundle_dir = tmp_path / "bundle-1"
    bundle_dir.mkdir()
    (bundle_dir / "model.joblib").write_bytes(b"x" * 1000)
    (bundle_dir / "manifest.json").write_bytes(b"y" * 234)
    nested = bundle_dir / "extras"
    nested.mkdir()
    (nested / "notes.txt").write_bytes(b"z" * 66)
    size = _bundle_directory_size_bytes(bundle_dir / "manifest.json")
    assert size == 1000 + 234 + 66


def test_bundle_local_identity_hashes_and_verifies_exact_artifact_bytes(tmp_path) -> None:
    bundle_dir = tmp_path / "bundle-identity"
    bundle_dir.mkdir()
    model = bundle_dir / "model.joblib"
    preprocessor = bundle_dir / "preprocessor.joblib"
    model.write_bytes(b"model-bytes")
    preprocessor.write_bytes(b"preprocessor-bytes")
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    preprocessor_sha = hashlib.sha256(preprocessor.read_bytes()).hexdigest()
    manifest = bundle_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": {
                    "model": {"filename": model.name, "sha256": model_sha},
                    "preprocessor": {
                        "filename": preprocessor.name,
                        "sha256": preprocessor_sha,
                    },
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    identity = _bundle_local_identity(manifest)

    assert identity == {
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "model_artifact_sha256": model_sha,
        "preprocessor_artifact_sha256": preprocessor_sha,
    }


def test_bundle_local_identity_rejects_artifact_hash_mismatch(tmp_path) -> None:
    bundle_dir = tmp_path / "bundle-mismatch"
    bundle_dir.mkdir()
    (bundle_dir / "model.joblib").write_bytes(b"model-bytes")
    (bundle_dir / "preprocessor.joblib").write_bytes(b"preprocessor-bytes")
    manifest = bundle_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": {
                    "model": {"filename": "model.joblib", "sha256": "0" * 64},
                    "preprocessor": {
                        "filename": "preprocessor.joblib",
                        "sha256": "0" * 64,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="model artifact SHA-256"):
        _bundle_local_identity(manifest)


def test_genuine_model_benchmark_evidence_is_complete_and_locally_rebindable() -> None:
    repository = Path(__file__).resolve().parents[1]
    manifest_path = repository / "artifacts/historical-reference-demo-v1/manifest.json"
    input_path = repository / "reports/operations/2026-08-25_genuine_model_benchmark_input.json"
    report_path = repository / "reports/operations/2026-08-25_genuine_model_api_benchmark.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload == {
        "Time": 0.0,
        **{f"V{index}": 0.0 for index in range(1, 29)},
        "Amount": 1.0,
    }
    assert report["endpoint"] == "/v1/predict"
    assert report["payload_mix"] == "single_fixed_payload"
    assert report["request_count"] == 500
    assert report["successful_count"] == 500
    assert report["error_count"] == 0
    assert report["error_breakdown"] == {
        "invalid_contract_count": 0,
        "non_2xx_count": 0,
        "timeout_count": 0,
        "transport_error_count": 0,
    }
    assert report["bundle_fingerprint"] == {
        "model_version": "historical-reference-xgboost-20260624-demo-v1",
        "bundle_format_version": "3",
        "training_data_fingerprint": (
            "76e867c9809da64a34ee45e0895cae03b1aea233af5b901384cd6d958f5dac13"
        ),
    }
    assert report["bundle_local_identity"] == {
        "manifest_sha256": "e355834d916ab3951e3069fc38ce286dd3e3abe4251c8643c4d859cd781bbbf0",
        "model_artifact_sha256": (
            "5ce63f1a7efa5625fbaa61177e76a548fd9ccc1c3f0a1530ccff835cf8b1dc73"
        ),
        "preprocessor_artifact_sha256": (
            "07d4a9f49448b6aa09a41c5c71dbaff5172a5fb5c870154d284671f323c7862f"
        ),
    }
    assert report["bundle_size_bytes"] == 490_948
    assert report["core_model_inference_llm_tokens"] == 0
    for field in ("p50", "p95", "p99", "max"):
        assert math.isfinite(report["latency_ms"][field])
        assert report["latency_ms"][field] >= 0.0
    assert report["successful_throughput_requests_per_second"] > 0.0
    assert report["cold_start_seconds"] > 0.0
    assert report["peak_cpu_percent"] >= 0.0
    assert report["peak_memory_kib"] > 0

    # Model weights are intentionally ignored. When the authorized local bundle
    # is available, recompute the recorded binding; clean clones still validate
    # the complete committed evidence contract above without inventing bytes.
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload == manifest["golden_probe"]["features"]
        assert report["bundle_fingerprint"] == {
            "model_version": manifest["model_version"],
            "bundle_format_version": manifest["bundle_format_version"],
            "training_data_fingerprint": manifest["training_data_fingerprint"],
        }
        assert report["bundle_local_identity"] == _bundle_local_identity(manifest_path)
        assert report["bundle_size_bytes"] == _bundle_directory_size_bytes(manifest_path)


def _fake_stage(canned: dict[int, dict[str, object]], calls: list[int]):
    def _run(*, url: str, payload: dict, requests: int, concurrency: int, timeout_seconds: float):
        calls.append(concurrency)
        return canned[concurrency]

    return _run


def _stage_result(*, error_rate: float, p95: float, health_status: int) -> dict[str, object]:
    return {
        "error_rate": error_rate,
        "latency_ms": {"p95": p95},
        "health_probe": {"status": health_status},
    }


def test_ramp_rejects_empty_concurrency_levels() -> None:
    with pytest.raises(ValueError, match="empty"):
        run_progressive_load_test(
            url="http://127.0.0.1:1",
            payload={},
            concurrency_levels=[],
            requests_per_stage=10,
            timeout_seconds=1.0,
        )


@pytest.mark.parametrize("levels", [[4, 2, 1], [1, 2, 2, 4], [2, 1]])
def test_ramp_rejects_non_ascending_or_repeated_levels(levels: list[int]) -> None:
    with pytest.raises(ValueError, match="ascending"):
        run_progressive_load_test(
            url="http://127.0.0.1:1",
            payload={},
            concurrency_levels=levels,
            requests_per_stage=10,
            timeout_seconds=1.0,
        )


def test_ramp_rejects_out_of_bounds_requests_per_stage() -> None:
    with pytest.raises(ValueError, match="requests_per_stage"):
        run_progressive_load_test(
            url="http://127.0.0.1:1",
            payload={},
            concurrency_levels=[1, 2],
            requests_per_stage=0,
            timeout_seconds=1.0,
        )


def test_ramp_completes_all_levels_when_every_stage_is_within_bounds() -> None:
    canned = {
        level: _stage_result(error_rate=0.0, p95=10.0, health_status=200) for level in (1, 2, 4, 8)
    }
    calls: list[int] = []
    result = run_progressive_load_test(
        url="http://127.0.0.1:1",
        payload={},
        concurrency_levels=[1, 2, 4, 8],
        requests_per_stage=10,
        timeout_seconds=1.0,
        stage_runner=_fake_stage(canned, calls),
    )
    assert result["completed_all_levels"] is True
    assert result["stopped_reason"] is None
    assert result["stopped_at_concurrency"] is None
    assert calls == [1, 2, 4, 8]
    assert len(result["stages"]) == 4


def test_ramp_stops_on_error_rate_and_does_not_run_further_stages() -> None:
    canned = {
        1: _stage_result(error_rate=0.0, p95=10.0, health_status=200),
        2: _stage_result(error_rate=0.5, p95=10.0, health_status=200),
        4: _stage_result(error_rate=0.0, p95=10.0, health_status=200),
    }
    calls: list[int] = []
    result = run_progressive_load_test(
        url="http://127.0.0.1:1",
        payload={},
        concurrency_levels=[1, 2, 4],
        requests_per_stage=10,
        timeout_seconds=1.0,
        stop_criteria=RampStopCriteria(max_error_rate=0.01),
        stage_runner=_fake_stage(canned, calls),
    )
    assert result["stopped_reason"] == "error_rate_exceeded"
    assert result["stopped_at_concurrency"] == 2
    assert result["completed_all_levels"] is False
    assert calls == [1, 2]  # never reaches level 4


def test_ramp_stops_on_p95_latency_exceeded() -> None:
    canned = {
        1: _stage_result(error_rate=0.0, p95=10.0, health_status=200),
        2: _stage_result(error_rate=0.0, p95=999.0, health_status=200),
    }
    calls: list[int] = []
    result = run_progressive_load_test(
        url="http://127.0.0.1:1",
        payload={},
        concurrency_levels=[1, 2],
        requests_per_stage=10,
        timeout_seconds=1.0,
        stop_criteria=RampStopCriteria(max_p95_latency_ms=500.0),
        stage_runner=_fake_stage(canned, calls),
    )
    assert result["stopped_reason"] == "p95_latency_exceeded"
    assert result["stopped_at_concurrency"] == 2


def test_ramp_stops_on_health_probe_degraded() -> None:
    canned = {
        1: _stage_result(error_rate=0.0, p95=10.0, health_status=200),
        2: _stage_result(error_rate=0.0, p95=10.0, health_status=503),
    }
    calls: list[int] = []
    result = run_progressive_load_test(
        url="http://127.0.0.1:1",
        payload={},
        concurrency_levels=[1, 2],
        requests_per_stage=10,
        timeout_seconds=1.0,
        stage_runner=_fake_stage(canned, calls),
    )
    assert result["stopped_reason"] == "health_probe_degraded"
    assert result["stopped_at_concurrency"] == 2
