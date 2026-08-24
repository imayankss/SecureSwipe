export function CostBreakdownChart({
  items,
  total,
}: {
  items: Array<{ label: string; value: number; tone: string }>;
  total: number;
}) {
  return (
    <div className="rounded-md border border-white/[0.08] bg-slate-950/35 p-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="ss-eyebrow text-amber-200">Illustrative cost composition</p>
          <p className="mt-1 text-xs text-slate-400">Relative contribution of the four existing arithmetic components.</p>
        </div>
        <span className="text-[10px] text-slate-500">display-only waterfall</span>
      </div>
      <div className="mt-4 grid gap-3">
        {items.map((item) => {
          const share = total > 0 ? (item.value / total) * 100 : 0;
          return (
            <div key={item.label}>
              <div className="flex items-center justify-between gap-4 text-[11px]">
                <span className="text-slate-300">{item.label}</span>
                <span className="ss-number text-slate-500">{share.toFixed(1)}%</span>
              </div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/[0.055]" role="img" aria-label={`${item.label}: ${share.toFixed(1)} percent of illustrative total`}>
                <div className={`h-full min-w-[2px] rounded-full ${item.tone}`} style={{ width: `${Math.max(share, item.value > 0 ? 0.8 : 0)}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

