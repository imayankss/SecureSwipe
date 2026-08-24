/**
 * Synthetic plumbing-test fixture generator.
 *
 * This module is a pure, deterministic, in-browser simulator that
 * demonstrates the SHAPE of a real-time decisioning pipeline (event ->
 * bounded contextual features -> bounded heuristic score -> decision).
 *
 * It is entirely disconnected from the historical PCA/XGBoost model and the
 * genuine-inference API. It never makes a network request, never touches a
 * database, and its `context_signal_score` is explicitly NOT a fraud
 * probability and NOT the historical model's score. Every value produced
 * here carries the evidence type `synthetic_plumbing_test` and must never be
 * displayed next to, or confused with, `historical_evaluation` or
 * `genuine_demo_inference` evidence.
 *
 * Determinism: a fixed seed produces the exact same sequence of events on
 * every load, satisfying the "fixed seeds and fixed clocks in tests"
 * requirement. Re-seeding (via `createSimulator`) starts a fresh, equally
 * deterministic sequence.
 */

// ---------------------------------------------------------------------------
// Deterministic PRNG (mulberry32) — no Math.random, fully reproducible.
// ---------------------------------------------------------------------------
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------------------------
// Types — mirrors context.md's canonical synthetic contract.
// ---------------------------------------------------------------------------
export type SyntheticOutcome = "success" | "declined" | "failed";
export type SyntheticDecision = "below_review_threshold" | "human_review" | "unavailable_fail_closed";

export interface SyntheticEventInput {
  event_id: string;
  event_time: string; // ISO-8601 UTC
  account_id: string;
  device_id: string;
  payment_method_id: string;
  merchant_id: string;
  address_id: string;
  ip_id: string;
  amount: number;
  currency: "INR";
  outcome: SyntheticOutcome;
  account_country: string;
  event_country: string;
  event_region: string;
  billing_shipping_match: boolean;
  vpn_or_proxy: boolean;
  retry_group_id: string | null;
}

export interface TriggeredSignal {
  code: string;
  family: string;
  explanation: string;
  contribution: number;
}

export interface WindowFeatureBucket {
  count: number;
  amountTotal: number;
}

export interface WindowFeatures {
  account: { "1m": WindowFeatureBucket; "1h": WindowFeatureBucket; "24h": WindowFeatureBucket };
  device: { "1m": WindowFeatureBucket; "1h": WindowFeatureBucket; "24h": WindowFeatureBucket };
  paymentMethod: { "1m": WindowFeatureBucket; "1h": WindowFeatureBucket; "24h": WindowFeatureBucket };
  merchant: { "1m": WindowFeatureBucket; "1h": WindowFeatureBucket; "24h": WindowFeatureBucket };
}

export interface SyntheticDecisionOutput {
  evidence_type: "synthetic_plumbing_test";
  event_id: string;
  request_id: string;
  schema_version: "1.0";
  processed_at: string; // ISO-8601 UTC
  latency_ms: number;
  decision: SyntheticDecision;
  context_signal_score: number; // bounded [0, 1]; not a fraud probability
  triggered_signals: TriggeredSignal[];
  window_features: WindowFeatures;
  is_duplicate: boolean;
  is_late_or_out_of_order: boolean;
}

export interface SyntheticEventRecord {
  input: SyntheticEventInput;
  output: SyntheticDecisionOutput;
}

// ---------------------------------------------------------------------------
// Fixed synthetic token pools — opaque, non-reversible, clearly fake.
// ---------------------------------------------------------------------------
const ACCOUNT_POOL = ["syn_acct_001", "syn_acct_002", "syn_acct_003", "syn_acct_004"];
const DEVICE_POOL = ["syn_dev_101", "syn_dev_102", "syn_dev_103", "syn_dev_104", "syn_dev_105"];
const PAYMENT_METHOD_POOL = ["syn_pm_201", "syn_pm_202", "syn_pm_203"];
const MERCHANT_POOL = ["syn_merchant_301", "syn_merchant_302"];
const ADDRESS_POOL = ["syn_addr_401", "syn_addr_402", "syn_addr_403"];
const IP_POOL = ["syn_ip_501", "syn_ip_502", "syn_ip_503", "syn_ip_504"];
const REGION_POOL = ["syn_region_north", "syn_region_south", "syn_region_east", "syn_region_west"];
const COUNTRY_POOL = ["syn_country_a", "syn_country_b"];

const MAX_RETAINED_EVENTS = 50; // bounded memory; oldest events are deterministically evicted
const MAX_VALID_AMOUNT = 200_000; // minor units; above this the simulator fails closed
const REVIEW_SCORE_THRESHOLD = 0.75;

function pick<T>(pool: readonly T[], rand: () => number): T {
  return pool[Math.floor(rand() * pool.length) % pool.length];
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

// ---------------------------------------------------------------------------
// Simulator: holds only in-memory, single-process, demo-only state.
// ---------------------------------------------------------------------------
export interface SimulatorOptions {
  seed?: number;
  /** Starting synthetic clock time; advances deterministically per event. */
  startTime?: string;
}

export class SyntheticPlumbingSimulator {
  private rand: () => number;
  private clockMs: number;
  private sequence = 0;
  private events: SyntheticEventRecord[] = [];
  private byEventId = new Map<string, SyntheticEventRecord>();
  private latestTimeByAccount = new Map<string, number>();

  constructor(options: SimulatorOptions = {}) {
    this.rand = mulberry32(options.seed ?? 42);
    this.clockMs = options.startTime ? Date.parse(options.startTime) : Date.parse("2026-01-05T09:00:00.000Z");
  }

  getEvents(): SyntheticEventRecord[] {
    return [...this.events];
  }

  reset(options: SimulatorOptions = {}): void {
    this.rand = mulberry32(options.seed ?? 42);
    this.clockMs = options.startTime ? Date.parse(options.startTime) : Date.parse("2026-01-05T09:00:00.000Z");
    this.sequence = 0;
    this.events = [];
    this.byEventId.clear();
    this.latestTimeByAccount.clear();
  }

  /** Re-submits an already-seen event_id. Deterministically idempotent: never rewrites the original decision. */
  replay(eventId: string): SyntheticEventRecord | null {
    const existing = this.byEventId.get(eventId);
    if (!existing) return null;
    this.sequence += 1;
    const duplicateOutput: SyntheticDecisionOutput = {
      ...existing.output,
      request_id: `syn_req_${this.sequence.toString().padStart(4, "0")}`,
      processed_at: new Date(this.clockMs).toISOString(),
      is_duplicate: true,
    };
    const record: SyntheticEventRecord = { input: existing.input, output: duplicateOutput };
    this.pushRecord(record, { evictOldest: true, indexById: false });
    return record;
  }

  /** Generates an intentionally invalid (out-of-bounds amount) event to demonstrate the fail-closed path. */
  generateInvalidEvent(): SyntheticEventRecord {
    return this.generate({ forceInvalidAmount: true });
  }

  /** Generates the next deterministic synthetic event. */
  generateEvent(): SyntheticEventRecord {
    return this.generate({});
  }

  private generate(opts: { forceInvalidAmount?: boolean }): SyntheticEventRecord {
    const rand = this.rand;
    this.sequence += 1;
    this.clockMs += 15_000 + Math.floor(rand() * 90_000); // advance 15s-105s per event

    const accountId = pick(ACCOUNT_POOL, rand);
    const deviceId = pick(DEVICE_POOL, rand);
    const paymentMethodId = pick(PAYMENT_METHOD_POOL, rand);
    const merchantId = pick(MERCHANT_POOL, rand);
    const addressId = pick(ADDRESS_POOL, rand);
    const ipId = pick(IP_POOL, rand);
    const accountCountry = pick(COUNTRY_POOL, rand);
    const eventCountry = rand() < 0.15 ? pick(COUNTRY_POOL, rand) : accountCountry;
    const eventRegion = pick(REGION_POOL, rand);
    const billingShippingMatch = rand() > 0.2;
    const vpnOrProxy = rand() < 0.15;
    const isRetry = rand() < 0.2;
    const outcome: SyntheticOutcome = isRetry ? (rand() < 0.6 ? "declined" : "failed") : "success";
    const baseAmount = 200 + Math.floor(rand() * 15_000);
    const amount = opts.forceInvalidAmount ? MAX_VALID_AMOUNT + 50_000 + Math.floor(rand() * 50_000) : baseAmount;

    const eventTimeIso = new Date(this.clockMs).toISOString();
    const eventId = `syn_evt_${this.sequence.toString().padStart(4, "0")}`;

    const input: SyntheticEventInput = {
      event_id: eventId,
      event_time: eventTimeIso,
      account_id: accountId,
      device_id: deviceId,
      payment_method_id: paymentMethodId,
      merchant_id: merchantId,
      address_id: addressId,
      ip_id: ipId,
      amount,
      currency: "INR",
      outcome,
      account_country: accountCountry,
      event_country: eventCountry,
      event_region: eventRegion,
      billing_shipping_match: billingShippingMatch,
      vpn_or_proxy: vpnOrProxy,
      retry_group_id: isRetry ? `syn_retry_${Math.floor(this.sequence / 3)}` : null,
    };

    const isLate = this.isLateOrOutOfOrder(accountId, this.clockMs);
    this.latestTimeByAccount.set(accountId, Math.max(this.latestTimeByAccount.get(accountId) ?? 0, this.clockMs));

    if (opts.forceInvalidAmount) {
      const output: SyntheticDecisionOutput = {
        evidence_type: "synthetic_plumbing_test",
        event_id: eventId,
        request_id: `syn_req_${this.sequence.toString().padStart(4, "0")}`,
        schema_version: "1.0",
        processed_at: new Date(this.clockMs).toISOString(),
        latency_ms: 4 + Math.floor(rand() * 6),
        decision: "unavailable_fail_closed",
        context_signal_score: 0,
        triggered_signals: [
          {
            code: "amount_bounds_violation",
            family: "unusual_amount",
            explanation: `Synthetic amount ${amount} exceeds the demo's configured maximum of ${MAX_VALID_AMOUNT}; the simulator fails closed instead of scoring it.`,
            contribution: 0,
          },
        ],
        window_features: this.computeWindowFeatures(accountId, deviceId, paymentMethodId, merchantId, this.clockMs),
        is_duplicate: false,
        is_late_or_out_of_order: isLate,
      };
      const record: SyntheticEventRecord = { input, output };
      this.pushRecord(record, { evictOldest: true, indexById: true });
      return record;
    }

    const windowFeatures = this.computeWindowFeatures(accountId, deviceId, paymentMethodId, merchantId, this.clockMs);
    const { triggeredSignals, score } = this.scoreEvent(input, windowFeatures, rand);
    const decision: SyntheticDecision = score >= REVIEW_SCORE_THRESHOLD ? "human_review" : "below_review_threshold";

    const output: SyntheticDecisionOutput = {
      evidence_type: "synthetic_plumbing_test",
      event_id: eventId,
      request_id: `syn_req_${this.sequence.toString().padStart(4, "0")}`,
      schema_version: "1.0",
      processed_at: new Date(this.clockMs).toISOString(),
      latency_ms: 4 + Math.floor(rand() * 6),
      decision,
      context_signal_score: Number(score.toFixed(3)),
      triggered_signals: triggeredSignals,
      window_features: windowFeatures,
      is_duplicate: false,
      is_late_or_out_of_order: isLate,
    };

    const record: SyntheticEventRecord = { input, output };
    this.pushRecord(record, { evictOldest: true, indexById: true });
    return record;
  }

  private isLateOrOutOfOrder(accountId: string, eventTimeMs: number): boolean {
    const latest = this.latestTimeByAccount.get(accountId);
    return latest !== undefined && eventTimeMs < latest;
  }

  private pushRecord(record: SyntheticEventRecord, opts: { evictOldest: boolean; indexById: boolean }): void {
    this.events.push(record);
    if (opts.indexById) this.byEventId.set(record.input.event_id, record);
    if (opts.evictOldest && this.events.length > MAX_RETAINED_EVENTS) {
      const evicted = this.events.shift();
      if (evicted && this.byEventId.get(evicted.input.event_id) === evicted) {
        this.byEventId.delete(evicted.input.event_id);
      }
    }
  }

  private computeWindowFeatures(
    accountId: string,
    deviceId: string,
    paymentMethodId: string,
    merchantId: string,
    nowMs: number,
  ): WindowFeatures {
    const windows: Array<[keyof WindowFeatures["account"], number]> = [
      ["1m", 60_000],
      ["1h", 3_600_000],
      ["24h", 86_400_000],
    ];
    const bucketFor = (key: "account_id" | "device_id" | "payment_method_id" | "merchant_id", value: string) => {
      const result = {} as Record<"1m" | "1h" | "24h", WindowFeatureBucket>;
      for (const [label, spanMs] of windows) {
        const inWindow = this.events.filter(
          (record) => record.input[key] === value && nowMs - Date.parse(record.input.event_time) <= spanMs,
        );
        result[label] = {
          count: Math.min(inWindow.length, MAX_RETAINED_EVENTS),
          amountTotal: Number(inWindow.reduce((total, record) => total + record.input.amount, 0).toFixed(2)),
        };
      }
      return result as WindowFeatures["account"];
    };
    return {
      account: bucketFor("account_id", accountId),
      device: bucketFor("device_id", deviceId),
      paymentMethod: bucketFor("payment_method_id", paymentMethodId),
      merchant: bucketFor("merchant_id", merchantId),
    };
  }

  private scoreEvent(
    input: SyntheticEventInput,
    windowFeatures: WindowFeatures,
    rand: () => number,
  ): { triggeredSignals: TriggeredSignal[]; score: number } {
    const triggeredSignals: TriggeredSignal[] = [];

    // 1. Device identity/newness
    const deviceSeenBefore = this.events.some((record) => record.input.device_id === input.device_id);
    if (!deviceSeenBefore) {
      triggeredSignals.push({
        code: "device_first_seen",
        family: "device_identity_newness",
        explanation: "This synthetic device token has not appeared earlier in this demo session.",
        contribution: 0.12,
      });
    }

    // 2. Transaction velocity
    if (windowFeatures.account["1h"].count >= 3) {
      triggeredSignals.push({
        code: "account_velocity_1h",
        family: "transaction_velocity",
        explanation: `${windowFeatures.account["1h"].count} synthetic events on this account within the last simulated hour.`,
        contribution: 0.18,
      });
    }

    // 3. Address patterns
    if (!input.billing_shipping_match) {
      triggeredSignals.push({
        code: "billing_shipping_mismatch",
        family: "address_patterns",
        explanation: "Synthetic billing and shipping address tokens do not match.",
        contribution: 0.1,
      });
    }

    // 4. Payment-method history
    const paymentMethodSeenBefore = this.events.some(
      (record) => record.input.account_id === input.account_id && record.input.payment_method_id === input.payment_method_id,
    );
    if (!paymentMethodSeenBefore) {
      triggeredSignals.push({
        code: "account_payment_method_novelty",
        family: "payment_method_history",
        explanation: "This synthetic account/payment-method pairing has not appeared earlier in this demo session.",
        contribution: 0.08,
      });
    }

    // 5. Geography/IP/VPN
    if (input.event_country !== input.account_country) {
      triggeredSignals.push({
        code: "country_mismatch",
        family: "geography_ip_vpn",
        explanation: "Synthetic event country differs from the synthetic account's home country.",
        contribution: 0.15,
      });
    }
    if (input.vpn_or_proxy) {
      triggeredSignals.push({
        code: "vpn_or_proxy_flag",
        family: "geography_ip_vpn",
        explanation: "Synthetic VPN/proxy indicator is set for this event.",
        contribution: 0.1,
      });
    }

    // 6. Unusual amount
    const priorAccountAmounts = this.events
      .filter((record) => record.input.account_id === input.account_id)
      .map((record) => record.input.amount);
    const baseline = priorAccountAmounts.length
      ? priorAccountAmounts.reduce((total, value) => total + value, 0) / priorAccountAmounts.length
      : input.amount;
    if (input.amount > baseline * 2.5 && priorAccountAmounts.length > 0) {
      triggeredSignals.push({
        code: "amount_deviation_from_account_baseline",
        family: "unusual_amount",
        explanation: "Synthetic amount is more than 2.5x this account's simulated running-average amount.",
        contribution: 0.14,
      });
    }

    // 7. Retry/failure behavior
    if (input.retry_group_id) {
      triggeredSignals.push({
        code: "retry_group_present",
        family: "retry_failure_behavior",
        explanation: "This synthetic event belongs to a simulated retry group.",
        contribution: 0.1,
      });
    }
    if (input.outcome !== "success") {
      triggeredSignals.push({
        code: "non_success_outcome",
        family: "retry_failure_behavior",
        explanation: `Synthetic outcome recorded as "${input.outcome}".`,
        contribution: 0.06,
      });
    }

    // 8. Merchant-specific behavior
    if (windowFeatures.merchant["1h"].count >= 4) {
      triggeredSignals.push({
        code: "merchant_velocity_1h",
        family: "merchant_specific_behavior",
        explanation: `${windowFeatures.merchant["1h"].count} synthetic events at this merchant within the last simulated hour.`,
        contribution: 0.09,
      });
    }

    const jitter = rand() * 0.03;
    const score = clamp(
      0.03 + jitter + triggeredSignals.reduce((total, signal) => total + signal.contribution, 0),
      0,
      0.97,
    );
    return { triggeredSignals, score };
  }
}

export function createSimulator(options?: SimulatorOptions): SyntheticPlumbingSimulator {
  return new SyntheticPlumbingSimulator(options);
}
