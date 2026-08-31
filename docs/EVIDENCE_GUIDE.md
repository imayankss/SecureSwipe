# Evidence guide

This page is the canonical entry point for understanding what each SecureSwipe
artifact can support. It does not replace the
[claim-to-evidence matrix](evidence/CLAIM_TO_EVIDENCE_MATRIX.md) or
[execution ledger](evidence/EXECUTION_LEDGER.md); those remain the authoritative
claim-status and chronological records.

## Reviewer path

A reviewer can establish the project boundary in under one minute:

1. Read the [README headline and workload trade-off](../README.md#headline-lane-a-result).
2. Open the [sealed Lane A result](evidence/LANE_A_FINAL_EVALUATION.md).
3. Confirm the exact public-claim status in the
   [claim-to-evidence matrix](evidence/CLAIM_TO_EVIDENCE_MATRIX.md).
4. Use [Architecture](ARCHITECTURE.md) to trace the offline, static, and local
   serving paths.
5. Use [Limitations](LIMITATIONS.md) before extending any claim beyond its
   recorded scope.
6. Use [Reproducibility](REPRODUCIBILITY.md) for data-free checks and local demo
   behavior.

## Evidence categories

Evidence categories describe provenance, not visual importance. A result cannot
move between categories because it looks similar or uses the same product name.

| Category | Supports | Does not support | Canonical source |
| --- | --- | --- | --- |
| Sealed Lane A evaluation | The one held-out IEEE-CIS evaluation, its aggregate metrics, calibration table, and capacity counts | Live performance, serving behavior, Razorpay performance, or a universal policy | [Lane A final evaluation](evidence/LANE_A_FINAL_EVALUATION.md) |
| Lane B historical evaluation | Preservation of the older already-observed random-holdout record | New model decisions, comparison with Lane A, or attribution to a served bundle | [Historical lock and matrix rows 2.x](evidence/CLAIM_TO_EVIDENCE_MATRIX.md#2--locked-historical-evaluation) |
| Historical/reference serving | Behavior of a verified local reference bundle and API | The Lane A headline result or proof that the bundle produced any historical metric | [Matrix rows 3.x](evidence/CLAIM_TO_EVIDENCE_MATRIX.md#3--genuine-model-inference-and-provenance) |
| Synthetic demonstration | Packaging, validation, failure, or workflow mechanics using generated fixtures | Fraud-model quality or real-transaction behavior | [API guide](API.md) |
| Illustrative cost scenario | Transparent arithmetic over published aggregate counts and editable assumptions | Savings, ROI, observed merchant economics, or an optimal capacity | [MT5 evidence](evidence/MT5_COST_EXPLORER_EVIDENCE.md) |
| Future or deferred | A named boundary or design that is explicitly absent | Any implemented capability | [Matrix rows 8.x](evidence/CLAIM_TO_EVIDENCE_MATRIX.md#8--deployment-status) |

## Lane A and Lane B are not comparable

Lane A and Lane B differ in corpus, feature space, label definition, base rate,
partitioning, model history, and evidence lifecycle. Their metrics must not be
placed in a comparison table, combined into one trend, or used to imply that one
serving bundle produced the other's result.

Lane A is the sole headline evaluation. Its committed record reports average
precision `0.208660`, ROC-AUC `0.814975`, and the review-capacity frontier.
[Source: Lane A aggregate metrics and capacity results.](evidence/LANE_A_FINAL_EVALUATION.md)

Lane B remains historical audit context. Its original fitted model, score vector,
runtime, and retained row identities are absent. The known local reference bundle
is historical-tainted and explicitly does not claim historical-metric linkage.

## P0.4 model/demo decision

P0.4 required a direct cryptographic chain from every serving artifact—model,
preprocessor, calibrator, ordered feature schema, and policy—to the sealed Lane A
result. That complete chain was unavailable or unproven.

The resulting boundary is mandatory:

> The interactive local/reference inference demonstration is deliberately
> separate from the sealed Lane A evaluation. The relationship is disclosed; it
> does not claim to serve the headline model.

The `/demo` route therefore uses a configured local reference API, a fixed
sanitized synthetic fixture, and fail-closed states. It may prove genuine local
estimator execution, audit receipt, same-process replay, and validation behavior.
It may not inherit Lane A metrics or identify its bundle as the headline model.

## Claim-to-evidence navigation

| Reviewer question | Read this first | Then inspect |
| --- | --- | --- |
| What is the headline result? | [Lane A final evaluation](evidence/LANE_A_FINAL_EVALUATION.md) | [Matrix §6A](evidence/CLAIM_TO_EVIDENCE_MATRIX.md#6a--lane-a-v2-development-evidence-separate-from-lane-b) |
| How was final access controlled? | [Final-evaluation protocol](evidence/LANE_A_FINAL_EVALUATION_PROTOCOL.md) | [Boundary amendment](evidence/LANE_A_FINAL_EVALUATION_PROTOCOL_BOUNDARY_AMENDMENT_1.md) |
| What does review capacity mean? | [Lane A §5](evidence/LANE_A_FINAL_EVALUATION.md#5--capacity-results) | [MT5 contract](evidence/MT5_COST_EXPLORER_CONTRACT.md) |
| What does the cost explorer prove? | [MT5 evidence](evidence/MT5_COST_EXPLORER_EVIDENCE.md) | [Limitations](LIMITATIONS.md#illustrative-cost-analysis) |
| Is the local demo the Lane A model? | [P0.4 decision above](#p04-modeldemo-decision) | [Architecture](ARCHITECTURE.md#model-and-evidence-boundary) |
| What does the API return? | [API guide](API.md) | [Model card](MODEL_CARD.md) |
| What fails closed? | [API runtime contract](API.md#runtime-contract) | [MT6 decision](evidence/MT6_STATE_AND_CRASH_DECISION.md) |
| What performance was measured? | [MT4 evidence](evidence/MT4_CONCURRENCY_EVIDENCE.md) | [Limitations](LIMITATIONS.md#serving-and-state) |
| Is a deployment tied to this source? | [Deployment integrity procedure](DEPLOYMENT.md#p05-deployment-to-source-sha-integrity) | [Matrix §8](evidence/CLAIM_TO_EVIDENCE_MATRIX.md#8--deployment-status) |
| Which checks can run without data? | [Reproducibility](REPRODUCIBILITY.md#data-free-deterministic-checks) | [Contributing](../CONTRIBUTING.md#required-checks) |

## Canonical records

The following files have deliberately different ownership:

- [Claim-to-evidence matrix](evidence/CLAIM_TO_EVIDENCE_MATRIX.md): whether a
  claim is verified, observed, inferred, proposed, or blocked.
- [Execution ledger](evidence/EXECUTION_LEDGER.md): what was done and in what
  order, including scoped gates and non-claims.
- [Lane A final evaluation](evidence/LANE_A_FINAL_EVALUATION.md): immutable
  aggregate outcome of the one final evaluation.
- [Release freeze](evidence/MT9_RELEASE_FREEZE.md): historical identity and
  verification record for that frozen local candidate.
- [Architecture](ARCHITECTURE.md): current implemented system shape.
- [Limitations](LIMITATIONS.md): complete claim and operating boundaries.
- [Deployment](DEPLOYMENT.md): release workflow and source-SHA integrity.
- [Reproducibility](REPRODUCIBILITY.md): environments, commands, and expected
  local behavior.

Historical records may contain old commit identities or test counts because they
describe a named past checkpoint. Do not copy those values into a current claim.

## Rules for adding evidence

1. Choose the evidence category before publishing a number.
2. Link every displayed metric directly to a committed aggregate artifact.
3. Keep row-level data, model bytes, score vectors, credentials, and private
   paths outside public documentation.
4. Record development evidence as development; do not relabel it as final.
5. Do not rerun or tune from the sealed Lane A result.
6. Treat a missing provenance edge as missing evidence, not as permission to
   infer the edge.
7. Update the matrix and ledger rather than duplicating their contents elsewhere.

## Evidence that is intentionally absent

- raw IEEE-CIS or Kaggle transaction rows;
- the exact cryptographically proven Lane A serving chain;
- a verified public backend;
- verified deployment-to-current-source linkage;
- merchant costs, customer outcomes, or production telemetry; and
- a verified pitch-video URL.

Absence is reported as a boundary. It is never filled with a placeholder,
reconstruction, or reference artifact.
