"""Bounded local load-harness validation tests."""

from __future__ import annotations

import pytest

from scripts.run_local_load_test import run_load_test


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
