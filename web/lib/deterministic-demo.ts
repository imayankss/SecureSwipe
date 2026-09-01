export const DEMO_FIXTURE_VERSION = "fixed-synthetic-v1";
export const DEMO_REQUEST_ID = "secureswipe-reference-demo-v1";
export const INVALID_DEMO_REQUEST_ID = "secureswipe-reference-demo-invalid-v1";

export const DEMO_FIXTURE = Object.freeze({
  Time: 0,
  V1: 0,
  V2: 0,
  V3: 0,
  V4: 0,
  V5: 0,
  V6: 0,
  V7: 0,
  V8: 0,
  V9: 0,
  V10: 0,
  V11: 0,
  V12: 0,
  V13: 0,
  V14: 0,
  V15: 0,
  V16: 0,
  V17: 0,
  V18: 0,
  V19: 0,
  V20: 0,
  V21: 0,
  V22: 0,
  V23: 0,
  V24: 0,
  V25: 0,
  V26: 0,
  V27: 0,
  V28: 0,
  Amount: 0,
} as const);

export const INVALID_DEMO_FIXTURE = Object.freeze({
  Time: "invalid-synthetic-value",
} as const);


/**
 * A recorded reference run.
 *
 * This is a fixed transcript of one previously observed response to
 * `DEMO_FIXTURE`, kept so a reviewer can walk the whole guided journey when no
 * reference API is running. It is replayed, never recomputed, and the UI always
 * labels it as a recorded transcript rather than a live inference.
 *
 * It deliberately carries no score field. The public response contract
 * suppresses the decision score, so the transcript does not store one either.
 */
export const RECORDED_RUN_LABEL = "Recorded reference run — replayed, not measured now";

export const RECORDED_REFERENCE_RUN = Object.freeze({
  schema_version: "1.0",
  request_id: DEMO_REQUEST_ID,
  score_type: "raw_score",
  operating_threshold: 0.53,
  decision: "human_review",
  model_version: "secureswipe-reference-bundle-1",
  bundle_format_version: "3",
  model_artifact_sha256:
    "960697c52608cb379612adbf0ce3b297a8d1e9b2c311d1f160374e09afd4ef19",
  audit_event_hash:
    "0e624d9dec46e9a752c1946a7031e84c6c277d62771e9e887f716f050b8ad90e",
} as const);
