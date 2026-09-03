# Scale benchmarks — a closed, negative record

**Verdict: `CLOSED WITHOUT SCALE CLAIM`.** SecureSwipe makes **no multi-worker
scalability or production-capacity claim.** This directory exists to show the work that
established that boundary, not to support a throughput number.

<p align="justify">
Eleven files may look like sprawl. They are the opposite: a pre-registered protocol, the
measurements taken under it, a reproduced defect, its repair, an independent confirmation of
that repair, and a final matrix that <b>failed closed</b> on a correctness gate. The honest
outcome of that sequence is silence on scale, and that silence is what this record buys.
</p>

> If you only read one file, read the
> [terminal closeout evidence](P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md). Everything else is the
> chain that justifies its verdict.

## Reading order

| # | File | What it establishes |
| --- | --- | --- |
| 1 | [P1_SCALE_PROTOCOL.md](P1_SCALE_PROTOCOL.md) | The pre-registered workload and measurement contract, fixed before any run |
| 2 | [P1_SCALE_HARNESS.md](P1_SCALE_HARNESS.md) | The runner implementing that contract — `postgres-scale` profile, single-item `POST /v2/predict` only |
| 3 | [P1_S4D_CLIENT_TRANSPORT_PROTOCOL.md](P1_S4D_CLIENT_TRANSPORT_PROTOCOL.md) · [evidence](P1_S4D_CLIENT_TRANSPORT_EVIDENCE.md) | Why the earlier P1-S4b matrix was invalid: the client submitted every attempt at once and rebuilt an HTTPX client per request |
| 4 | [P1_S4E_VALIDATED_HARNESS_PROTOCOL.md](P1_S4E_VALIDATED_HARNESS_PROTOCOL.md) · [evidence](P1_S4E_VALIDATED_HARNESS_EVIDENCE.md) | The corrected harness, and the state-store defect it exposed |
| 5 | [P1_S4F_STATE_STORE_DIAGNOSIS_PROTOCOL.md](P1_S4F_STATE_STORE_DIAGNOSIS_PROTOCOL.md) · [verification](P1_S4F_STATE_STORE_VERIFICATION_EVIDENCE.md) | Diagnosis and repair of the reproduced checkout-exhaustion defect |
| 6 | [P1_S4F_POSTFIX_VERIFICATION_PROTOCOL.md](P1_S4F_POSTFIX_VERIFICATION_PROTOCOL.md) | Three consecutive postfix proofs at the exact cell that had failed |
| 7 | [P1_S4_TERMINAL_CLOSEOUT_PROTOCOL.md](P1_S4_TERMINAL_CLOSEOUT_PROTOCOL.md) · **[closeout](P1_S4_TERMINAL_CLOSEOUT_EVIDENCE.md)** | The frozen 36-cell matrix, its failure at cell ten, and the decision to stop |

## What this record does and does not support

| Supports | Does not support |
| --- | --- |
| That a defect was found, repaired, and independently re-verified | Any throughput, latency, or concurrency figure for production |
| That the measurement contract was fixed *before* the runs | A deployable replica fleet, load balancer, or public availability |
| That the final matrix failed closed rather than being quietly retried | That the `postgres-scale` profile is the supported default — it is not; `local-default` is a single-process reference |

<p align="justify">
Every measurement here is loopback behaviour against a verified <b>reference</b> bundle on one
machine. It is not Razorpay-scale evidence and is never presented as such. Any future benchmark
must stay bound to its exact source SHA, hardware, worker count, and concurrency rather than
becoming a universal capacity claim.
</p>

**Related:** [Architecture](../ARCHITECTURE.md) ·
[Architecture gallery](../architecture/README.md#06--audit-integrity-and-recovery) ·
[Evidence guide](../EVIDENCE_GUIDE.md) ·
[Limitations](../LIMITATIONS.md)
