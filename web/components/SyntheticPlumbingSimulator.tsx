"use client";

import { useMemo, useState } from "react";
import {
  AlertOctagon,
  Copy,
  PlayCircle,
  RefreshCcw,
  ShieldAlert,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Section } from "@/components/Section";
import { EvidenceLabel } from "@/components/EvidenceLabel";
import { useCommandDisplayCurrency } from "@/components/dashboard/DisplayCurrencyContext";
import { SyntheticDecisionFlow } from "@/components/dashboard/SyntheticDecisionFlow";
import { SyntheticEventTable } from "@/components/dashboard/SyntheticEventTable";
import {
  DEFAULT_DISPLAY_CURRENCY,
  DISPLAY_CURRENCIES,
  ILLUSTRATIVE_INR_PER_USD,
  formatSyntheticInr,
  type DisplayCurrency,
} from "@/data/displayCurrency";
import {
  createSimulator,
  type SyntheticEventRecord,
  type SyntheticPlumbingSimulator as Simulator,
} from "@/data/syntheticFixture";

const DECISION_COPY: Record<string, { label: string; className: string }> = {
  below_review_threshold: {
    label: "Below review threshold",
    className: "text-emerald-100",
  },
  human_review: { label: "Human review", className: "text-amber-100" },
  unavailable_fail_closed: {
    label: "Unavailable / fail closed",
    className: "text-rose-100",
  },
};

function useSimulator() {
  const [simulator] = useState<Simulator>(() => createSimulator({ seed: 42 }));
  const [events, setEvents] = useState<SyntheticEventRecord[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(
    null,
  );

  function refresh(latest: SyntheticEventRecord) {
    setEvents([...simulator.getEvents()]);
    setSelectedRequestId(latest.output.request_id);
  }

  return {
    generate: () => refresh(simulator.generateEvent()),
    generateInvalid: () => refresh(simulator.generateInvalidEvent()),
    replay: () => {
      const last = events[events.length - 1];
      if (!last) return;
      const record = simulator.replay(last.input.event_id);
      if (record) refresh(record);
    },
    reset: () => {
      simulator.reset({ seed: 42 });
      setEvents([]);
      setSelectedRequestId(null);
    },
    events,
    selectedRequestId,
    setSelectedRequestId,
  };
}

export function SyntheticPlumbingSimulator() {
  const commandCurrency = useCommandDisplayCurrency();
  const {
    generate,
    generateInvalid,
    replay,
    reset,
    events,
    selectedRequestId,
    setSelectedRequestId,
  } = useSimulator();
  const [localDisplayCurrency, setLocalDisplayCurrency] = useState<DisplayCurrency>(
    DEFAULT_DISPLAY_CURRENCY,
  );
  const displayCurrency = commandCurrency?.displayCurrency ?? localDisplayCurrency;
  const setDisplayCurrency = commandCurrency?.setDisplayCurrency ?? setLocalDisplayCurrency;

  const selected = useMemo(
    () =>
      events.find((record) => record.output.request_id === selectedRequestId) ??
      events[events.length - 1] ??
      null,
    [events, selectedRequestId],
  );

  return (
    <Section
      id="synthetic"
      eyebrow="Real-time plumbing demonstration"
      title="Synthetic event, feature, and decision plumbing"
      description="A fully in-browser, fabricated event stream. No model, database, or network call is involved, and none of this reflects real-world fraud detection accuracy."
    >
      <Card className="border-violet-200/20">
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <CardTitle>Synthetic real-time decisioning demo</CardTitle>
                <EvidenceLabel type="synthetic-plumbing-test" />
              </div>
              <CardDescription>
                Demonstrates event → bounded contextual features → bounded
                heuristic score → decision plumbing across eight synthetic
                signal families. Single-process, in-browser, demo-only state.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {!commandCurrency ? <div className="flex flex-col gap-3 rounded-xl border border-violet-200/15 bg-violet-300/[0.04] p-4 text-sm text-slate-300 sm:flex-row sm:items-end sm:justify-between">
            <label
              className="grid gap-2 font-medium text-slate-200"
              htmlFor="synthetic-display-currency"
            >
              Synthetic amount display currency
              <select
                id="synthetic-display-currency"
                aria-describedby="synthetic-currency-note"
                className="rounded-lg border border-white/15 bg-slate-950/80 px-3 py-2 text-white shadow-inner shadow-black/20"
                value={displayCurrency}
                onChange={(event) =>
                  setDisplayCurrency(
                    event.currentTarget.value as DisplayCurrency,
                  )
                }
              >
                {DISPLAY_CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </select>
            </label>
            <p
              className="ss-prose max-w-2xl text-xs leading-5 text-slate-400"
              id="synthetic-currency-note"
            >
              INR is the default for fabricated example amounts. USD is a fixed
              illustrative display conversion at 1 USD = ₹
              {ILLUSTRATIVE_INR_PER_USD.toFixed(2)}; no live FX is fetched, and
              this never changes genuine-model input semantics.
            </p>
          </div> : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={generate}
              className="flex items-center gap-1.5 rounded-lg border border-violet-200/25 bg-violet-300/10 px-3 py-2 text-xs font-medium text-violet-100 transition hover:border-violet-200/40 hover:bg-violet-300/20"
            >
              <PlayCircle className="h-3.5 w-3.5" aria-hidden="true" />
              Generate next synthetic event
            </button>
            <button
              type="button"
              onClick={replay}
              disabled={events.length === 0}
              className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-violet-200/25 hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              Replay last event ID (duplicate)
            </button>
            <button
              type="button"
              onClick={generateInvalid}
              className="flex items-center gap-1.5 rounded-lg border border-rose-200/25 bg-rose-300/10 px-3 py-2 text-xs font-medium text-rose-100 transition hover:bg-rose-300/20"
            >
              <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
              Simulate out-of-bounds event (fail closed)
            </button>
            <button
              type="button"
              onClick={reset}
              className="ml-auto flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-violet-200/25 hover:bg-white/[0.08]"
            >
              <RefreshCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Reset demo session
            </button>
          </div>
          <p className="ss-prose flex items-start gap-2 rounded-xl border border-violet-200/15 bg-violet-300/[0.04] p-3 text-xs leading-5 text-slate-300">
            <AlertOctagon
              className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-200"
              aria-hidden="true"
            />
            Reset clears this browser tab&apos;s in-memory demo state only. It
            is not a recovery, backup, or reconciliation operation, and it never
            touches the historical evaluation or the genuine-inference API.
          </p>

          <SyntheticDecisionFlow record={selected} displayCurrency={displayCurrency} />

          {events.length === 0 ? (
            <p className="text-sm text-slate-400" role="status">
              No synthetic events yet. Generate one to see the pipeline run.
            </p>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[0.68fr_1.32fr]">
                <div className="rounded-md border border-white/[0.08] bg-slate-950/30 p-4">
                  <p className="ss-eyebrow text-slate-500">Selected event</p>
                  <p className="mt-2 text-sm font-medium text-white">Inspect the evidence emitted by the synthetic pipeline.</p>
                  <dl className="mt-4 grid gap-3 text-xs text-slate-400">
                    <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] pb-2">
                      <dt>Events retained</dt>
                      <dd className="ss-number text-white">{events.length}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] pb-2">
                      <dt>Session seed</dt>
                      <dd className="ss-number text-white">42</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt>State boundary</dt>
                      <dd className="text-white">This browser tab</dd>
                    </div>
                  </dl>
                </div>
                {selected ? <EventDetail record={selected} displayCurrency={displayCurrency} /> : null}
              </div>
              <SyntheticEventTable
                events={events}
                selectedRequestId={selected?.output.request_id ?? null}
                displayCurrency={displayCurrency}
                onSelect={setSelectedRequestId}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </Section>
  );
}

function EventDetail({
  record,
  displayCurrency,
}: {
  record: SyntheticEventRecord;
  displayCurrency: DisplayCurrency;
}) {
  const decisionCopy = DECISION_COPY[record.output.decision];
  return (
    <div className="space-y-4 rounded-xl border border-white/10 bg-slate-950/35 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-sm text-white">{record.input.event_id}</p>
        <p className={`text-sm font-medium ${decisionCopy?.className}`}>
          {decisionCopy?.label}
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs text-slate-300 sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">Context signal score</dt>
          <dd>
            {record.output.context_signal_score.toFixed(3)} (not a fraud
            probability)
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Synthetic example amount</dt>
          <dd>{formatSyntheticInr(record.input.amount, displayCurrency)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Outcome</dt>
          <dd>{record.input.outcome}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Account / device</dt>
          <dd className="font-mono">
            {record.input.account_id} / {record.input.device_id}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Request ID</dt>
          <dd className="font-mono">{record.output.request_id}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Latency</dt>
          <dd>{record.output.latency_ms} ms (simulated)</dd>
        </div>
      </dl>

      <div>
        <p className="ss-eyebrow mb-1.5 text-[0.64rem] text-slate-400">
          Triggered signals
        </p>
        {record.output.triggered_signals.length === 0 ? (
          <p className="text-xs text-slate-500">
            No signal families triggered for this synthetic event.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {record.output.triggered_signals.map((signal) => (
              <li
                key={signal.code}
                className="rounded-lg border border-white/10 bg-white/[0.02] p-2.5 text-xs text-slate-300"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-violet-200">
                    {signal.code}
                  </span>
                  <span className="text-slate-500">
                    +{signal.contribution.toFixed(2)}
                  </span>
                </div>
                <p className="mt-0.5 text-slate-400">{signal.explanation}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <p className="ss-eyebrow mb-1.5 text-[0.64rem] text-slate-400">
          Bounded window features (account)
        </p>
        <div className="grid grid-cols-3 gap-2 text-xs text-slate-300">
          {(["1m", "1h", "24h"] as const).map((windowLabel) => (
            <div
              key={windowLabel}
              className="rounded-lg border border-white/10 bg-white/[0.02] p-2"
            >
              <p className="text-slate-500">{windowLabel}</p>
              <p>
                {record.output.window_features.account[windowLabel].count}{" "}
                events
              </p>
              <p>
                {formatSyntheticInr(
                  record.output.window_features.account[windowLabel]
                    .amountTotal,
                  displayCurrency,
                )}{" "}
                total
              </p>
            </div>
          ))}
        </div>
      </div>

      {record.output.is_duplicate ? (
        <p className="text-xs text-amber-200">
          Duplicate submission of an existing event_id. Per the idempotency
          policy, the original decision was not rewritten.
        </p>
      ) : null}
      {record.output.is_late_or_out_of_order ? (
        <p className="text-xs text-amber-200">
          This event&apos;s timestamp is earlier than the latest event already
          processed for this account. Prior emitted decisions were not
          rewritten.
        </p>
      ) : null}
    </div>
  );
}
