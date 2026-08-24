import { EvidenceLabel } from "@/components/EvidenceLabel";
import { DashboardPanel } from "@/components/dashboard/DashboardPanel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { dashboardData, formatInteger } from "@/data/metrics";

export function HistoricalDatasetPanel() {
  const dataset = dashboardData.dataset;
  return (
    <DashboardPanel
      eyebrow="Historical benchmark"
      title="Why the problem is hard"
      description={`Fraud is ${dataset.fraudPrevalencePercent.toFixed(4)}% of this tracked public benchmark.`}
      aside={<EvidenceLabel type="historical-evaluation" />}
      bodyClassName="space-y-5 p-5 sm:p-6"
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-2">
        {[
          ["Transactions", formatInteger(dataset.totalTransactions)],
          ["Fraud", formatInteger(dataset.fraudTransactions)],
          ["Prevalence", `${dataset.fraudPrevalencePercent.toFixed(4)}%`],
          ["Imbalance", `${dataset.imbalanceRatio.toFixed(2)} : 1`],
        ].map(([label, value]) => (
          <div className="rounded-md border border-white/[0.08] bg-slate-950/40 p-3" key={label}>
            <p className="ss-eyebrow text-slate-500">{label}</p>
            <p className="ss-number mt-2 text-xl font-semibold text-white">{value}</p>
          </div>
        ))}
      </div>

      <div>
        <div className="flex items-center justify-between text-[11px] text-slate-500">
          <span>Legitimate {formatInteger(dataset.legitimateTransactions)}</span>
          <span>Fraud {formatInteger(dataset.fraudTransactions)}</span>
        </div>
        <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-slate-900" role="img" aria-label="Historical class imbalance">
          <span className="h-full min-w-[3px] bg-teal-300" style={{ width: `${100 - dataset.fraudPrevalencePercent}%` }} />
          <span className="h-full min-w-[3px] bg-amber-300" style={{ width: `${dataset.fraudPrevalencePercent}%` }} />
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border border-white/[0.08]">
        <Table>
          <THead>
            <TR>
              <TH>Split</TH>
              <TH>Rows</TH>
              <TH>Legitimate</TH>
              <TH>Fraud</TH>
            </TR>
          </THead>
          <TBody>
            {dataset.splits.map((split) => (
              <TR key={split.name}>
                <TD className="capitalize text-white">{split.name}</TD>
                <TD>{formatInteger(split.rows)}</TD>
                <TD>{formatInteger(split.legitimate)}</TD>
                <TD>{formatInteger(split.fraud)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </div>
      <p className="text-[11.5px] leading-5 text-slate-500">
        A majority-class classifier reaches {dataset.majorityClassAccuracyPercent.toFixed(4)}% accuracy while detecting none of the fraud class.
      </p>
    </DashboardPanel>
  );
}
