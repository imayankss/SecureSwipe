"""Bounded local load-harness validation tests."""

from __future__ import annotations

import pytest

from scripts.run_local_load_test import (
    RampStopCriteria,
    _bundle_directory_size_bytes,
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
