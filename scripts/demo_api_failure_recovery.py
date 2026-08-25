"""Demonstrate bounded fail-closed recovery from a transient audit-sink failure."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from fastapi.testclient import TestClient

from api.audit import AuditLog, verify_audit_log
from api.main import ApiSettings, create_app
from api.service import ModelService
from src.artifacts.bundle import load_model_bundle
from src.preprocessing.feature_config import ALL_FEATURES

DEFAULT_ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts"
DEFAULT_BUNDLE_MANIFEST = DEFAULT_ARTIFACT_ROOT / "historical-reference-demo-v1" / "manifest.json"
BOUNDED_DECISIONS = {"human_review", "below_review_threshold"}


class FailOnceAuditSink:
    """Inject one pre-append write failure, then delegate normally."""

    def __init__(self, delegate: AuditLog) -> None:
        self._delegate = delegate
        self.attempts = 0

    def append_inference(self, **kwargs: Any) -> tuple[str, ...]:
        self.attempts += 1
        if self.attempts == 1:
            raise OSError("injected transient audit-sink failure")
        return self._delegate.append_inference(**kwargs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--bundle-manifest", type=Path, default=DEFAULT_BUNDLE_MANIFEST)
    parser.add_argument("--max-seconds", type=float, default=20.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_seconds <= 0:
        raise ValueError("--max-seconds must be positive.")

    started = time.perf_counter()
    bundle = load_model_bundle(
        args.bundle_manifest.expanduser().resolve(),
        trusted_root=args.artifact_root.expanduser().resolve(),
    )
    payload = {feature: 0.0 for feature in ALL_FEATURES}
    request_id = "audit-recovery-demo-1"

    with tempfile.TemporaryDirectory(prefix="secureswipe-failure-recovery-") as directory:
        audit_path = Path(directory) / "prediction-events.ndjson"
        settings = ApiSettings(
            artifact_root=args.artifact_root,
            bundle_manifest=None,
            cors_origins=(),
            audit_log_path=audit_path,
        )
        with TestClient(create_app(service=ModelService(bundle), settings=settings)) as client:
            sink = FailOnceAuditSink(client.app.state.audit_log)
            client.app.state.audit_log = sink
            headers = {"X-Request-ID": request_id}
            failed = client.post("/v1/predict", json=payload, headers=headers)
            recovered = client.post("/v1/predict", json=payload, headers=headers)
            replay = client.post("/v1/predict", json=payload, headers=headers)

        verified = verify_audit_log(audit_path)
        elapsed = time.perf_counter() - started
        failed_body = failed.json()
        recovered_body = recovered.json()

        checks = {
            "failed_closed": (
                failed.status_code == 503
                and failed_body.get("error", {}).get("code") == "audit_unavailable"
                and "decision" not in failed_body
            ),
            "recovered": (
                recovered.status_code == 200 and recovered_body.get("decision") in BOUNDED_DECISIONS
            ),
            "replayed_without_duplicate_event": (
                replay.status_code == 200
                and replay.json() == recovered_body
                and replay.headers.get("x-idempotent-replay") == "true"
                and verified.event_count == 1
                and sink.attempts == 2
            ),
            "under_deadline": elapsed < args.max_seconds,
        }
        summary = {
            "bundle_manifest": str(args.bundle_manifest.expanduser().resolve()),
            "model_fingerprint_sha256": bundle.model_artifact_sha256,
            "model_version": bundle.model_version,
            "elapsed_seconds": round(elapsed, 3),
            "failure_status": failed.status_code,
            "failure_error_code": failed_body.get("error", {}).get("code"),
            "recovery_status": recovered.status_code,
            "recovery_decision": recovered_body.get("decision"),
            "replay_status": replay.status_code,
            "audit_event_count": verified.event_count,
            "checks": checks,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        if not all(checks.values()):
            raise RuntimeError("Failure/recovery demonstration did not satisfy its contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
