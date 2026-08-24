import { formatSyntheticInr, type DisplayCurrency } from "@/data/displayCurrency";
import type { SyntheticEventRecord } from "@/data/syntheticFixture";

const decisionLabel = {
  below_review_threshold: "Below review threshold",
  human_review: "Human review",
  unavailable_fail_closed: "Unavailable / fail closed",
} as const;

export function SyntheticEventTable({
  events,
  selectedRequestId,
  displayCurrency,
  onSelect,
}: {
  events: SyntheticEventRecord[];
  selectedRequestId: string | null;
  displayCurrency: DisplayCurrency;
  onSelect: (requestId: string) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-white/[0.08] bg-slate-950/30">
      <table className="w-full min-w-[820px] border-collapse text-left text-[11px]" aria-label="Synthetic event timeline">
        <thead className="border-b border-white/[0.08] bg-white/[0.025] text-slate-500">
          <tr>
            {['Request ID', 'Event', 'Amount', 'Signals', 'Score', 'Decision', 'Latency', 'Evidence'].map((heading) => (
              <th key={heading} className="px-3 py-2.5 font-medium">{heading}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {events.slice().reverse().map((record) => {
            const selected = record.output.request_id === selectedRequestId;
            return (
              <tr
                key={`${record.input.event_id}-${record.output.request_id}`}
                className={`border-b border-white/[0.06] last:border-0 ${selected ? "bg-violet-300/[0.07]" : "hover:bg-white/[0.025]"}`}
              >
                <td className="p-0">
                  <button
                    type="button"
                    onClick={() => onSelect(record.output.request_id)}
                    aria-pressed={selected}
                    className="w-full px-3 py-3 text-left font-mono text-violet-100"
                  >
                    {record.output.request_id}
                  </button>
                </td>
                <td className="px-3 py-3 font-mono text-slate-300">{record.input.event_id}</td>
                <td className="ss-number px-3 py-3 text-slate-300">{formatSyntheticInr(record.input.amount, displayCurrency)}</td>
                <td className="ss-number px-3 py-3 text-slate-300">{record.output.triggered_signals.length}</td>
                <td className="ss-number px-3 py-3 text-slate-300">{record.output.context_signal_score.toFixed(3)}</td>
                <td className="px-3 py-3 text-slate-200">
                  {decisionLabel[record.output.decision]}
                  {record.output.is_duplicate ? <span className="block text-[10px] text-amber-200">duplicate</span> : null}
                </td>
                <td className="ss-number px-3 py-3 text-slate-400">{record.output.latency_ms} ms</td>
                <td className="px-3 py-3 text-violet-200">Synthetic plumbing test</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

