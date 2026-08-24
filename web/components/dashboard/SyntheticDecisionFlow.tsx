import type { ReactNode } from "react";
import type { SyntheticEventRecord } from "@/data/syntheticFixture";
import { formatSyntheticInr, type DisplayCurrency } from "@/data/displayCurrency";

const signalFamilies = [
  ["device_identity_newness", "Device identity"],
  ["transaction_velocity", "Velocity"],
  ["address_patterns", "Address pattern"],
  ["payment_method_history", "Payment history"],
  ["geography_ip_vpn", "Geography / IP"],
  ["unusual_amount", "Unusual amount"],
  ["retry_failure_behavior", "Retry / failure"],
  ["merchant_specific_behavior", "Merchant context"],
] as const;

const signalCenters = [55, 113, 171, 229, 287, 345, 403, 461] as const;

function flowDecision(record: SyntheticEventRecord | null) {
  if (!record) return "Awaiting event";
  if (record.output.decision === "human_review") return "Human review";
  if (record.output.decision === "unavailable_fail_closed") return "Unavailable · safe halt";
  return "Below review threshold";
}

export function SyntheticDecisionFlow({
  record,
  displayCurrency,
}: {
  record: SyntheticEventRecord | null;
  displayCurrency: DisplayCurrency;
}) {
  const activeFamilies = new Set(record?.output.triggered_signals.map((signal) => signal.family) ?? []);
  const failedClosed = record?.output.decision === "unavailable_fail_closed";
  const hasTriggeredSignals = activeFamilies.size > 0;
  const primaryPath = hasTriggeredSignals ? "#f6a83b" : record ? "#5eead4" : "#334155";
  const primaryMarker = hasTriggeredSignals ? "url(#flow-arrow-active)" : record ? "url(#flow-arrow-audit)" : "url(#flow-arrow-inactive)";

  return (
    <div
      className="rounded-md border border-white/[0.08] bg-[#07101d]"
      aria-label="Synthetic transaction decision flow"
    >
      <div className="overflow-x-auto overscroll-x-contain">
        <svg
          className="block h-auto min-w-[1160px] w-full"
          viewBox="0 0 1320 520"
          role="img"
          aria-labelledby="synthetic-flow-title synthetic-flow-description"
        >
          <title id="synthetic-flow-title">Synthetic transaction decision flow</title>
          <desc id="synthetic-flow-description">
            A fabricated transaction passes through validation, eight contextual signal families, scoring, human-review policy, and structured audit evidence. Triggered signal paths are highlighted.
          </desc>

          <defs>
            <marker id="flow-arrow-inactive" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
              <path d="M0 0 L8 4 L0 8 Z" fill="#475569" />
            </marker>
            <marker id="flow-arrow-active" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
              <path d="M0 0 L8 4 L0 8 Z" fill="#f6a83b" />
            </marker>
            <marker id="flow-arrow-audit" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="strokeWidth">
              <path d="M0 0 L8 4 L0 8 Z" fill="#5eead4" />
            </marker>
          </defs>

          <rect x="0" y="0" width="1320" height="520" fill="#07101d" />

          <g fill="none" strokeLinecap="round" strokeLinejoin="round">
            <path
              d="M170 260 C188 260 202 260 220 260"
              stroke={record ? "#5eead4" : "#334155"}
              strokeWidth="2"
              markerEnd={record ? "url(#flow-arrow-audit)" : "url(#flow-arrow-inactive)"}
            />

            {signalFamilies.map(([family], index) => {
              const active = activeFamilies.has(family);
              const y = signalCenters[index];
              return (
                <g key={`${family}-paths`}>
                  <path
                    d={`M400 260 C454 260 458 ${y} 510 ${y}`}
                    stroke={active ? "#f6a83b" : "#334155"}
                    strokeWidth={active ? "3" : "1.35"}
                    opacity={active ? "1" : "0.58"}
                    markerEnd={active ? "url(#flow-arrow-active)" : "url(#flow-arrow-inactive)"}
                  />
                  <path
                    d={`M780 ${y} C829 ${y} 798 260 845 260`}
                    stroke={active ? "#f6a83b" : "#334155"}
                    strokeWidth={active ? "3" : "1.35"}
                    opacity={active ? "1" : "0.58"}
                    markerEnd={active ? "url(#flow-arrow-active)" : "url(#flow-arrow-inactive)"}
                  />
                </g>
              );
            })}

            <path
              d="M965 260 C977 260 983 260 995 260"
              stroke={primaryPath}
              strokeWidth={hasTriggeredSignals ? "3" : "2"}
              markerEnd={primaryMarker}
            />
            <path
              d="M1145 260 C1161 260 1168 260 1184 260"
              stroke={record ? "#5eead4" : "#334155"}
              strokeWidth="2"
              markerEnd={record ? "url(#flow-arrow-audit)" : "url(#flow-arrow-inactive)"}
            />
          </g>

          <StageNode
            x={20}
            y={222}
            width={150}
            height={76}
            index="01"
            label="Transaction"
            active={Boolean(record)}
            tone="teal"
          >
            <tspan x="95" dy="18" className="font-mono">
              {record?.input.event_id ?? "synthetic event"}
            </tspan>
            <tspan x="95" dy="16">
              {record ? formatSyntheticInr(record.input.amount, displayCurrency) : "fabricated input"}
            </tspan>
          </StageNode>

          <StageNode
            x={220}
            y={222}
            width={180}
            height={76}
            index="02"
            label="Validation"
            active={Boolean(record)}
            tone={failedClosed ? "rose" : "teal"}
          >
            <tspan x="310" dy="18">
              {failedClosed ? "Bounds violation" : record ? "Schema accepted" : "schema + bounds"}
            </tspan>
            <tspan x="310" dy="16">
              {record?.output.is_duplicate ? "Idempotent replay" : "event ID checked"}
            </tspan>
          </StageNode>

          <text x="510" y="22" fill="#94a3b8" fontSize="10" fontWeight="700" letterSpacing="1.5">
            03 · CONTEXTUAL SIGNALS
          </text>
          <text x="780" y="22" fill="#64748b" fontSize="10" textAnchor="end">
            {record?.output.triggered_signals.length ?? 0}/8 active
          </text>

          {signalFamilies.map(([family, label], index) => {
            const active = activeFamilies.has(family);
            const y = signalCenters[index] - 21;
            return (
              <g key={family}>
                <rect
                  x="510"
                  y={y}
                  width="270"
                  height="42"
                  rx="8"
                  fill={active ? "rgba(246,168,59,.13)" : "rgba(15,23,42,.72)"}
                  stroke={active ? "#f6a83b" : "rgba(100,116,139,.34)"}
                  strokeWidth={active ? "1.5" : "1"}
                />
                <text
                  x="528"
                  y={y + 26}
                  fill={active ? "#f6a83b" : "#94a3b8"}
                  fontSize="13"
                  fontWeight={active ? "600" : "500"}
                >
                  {active ? "▲" : "·"} {label}
                </text>
              </g>
            );
          })}

          <StageNode
            x={845}
            y={215}
            width={120}
            height={90}
            index="04"
            label="Score"
            active={Boolean(record)}
            tone="violet"
          >
            <tspan x="905" dy="20" fill="#f8fafc" fontSize="17" fontWeight="700">
              {record ? record.output.context_signal_score.toFixed(3) : "—"}
            </tspan>
            <tspan x="905" dy="16">bounded heuristic</tspan>
          </StageNode>

          <StageNode
            x={995}
            y={215}
            width={150}
            height={90}
            index="05"
            label="Policy"
            active={Boolean(record)}
            tone={failedClosed ? "rose" : "amber"}
          >
            <tspan x="1070" dy="20">{flowDecision(record)}</tspan>
            <tspan x="1070" dy="16">human-review rule</tspan>
          </StageNode>

          <g>
            <text x="1194" y="224" fill="#64748b" fontSize="10" fontWeight="700" letterSpacing="1.5">
              06 · AUDIT
            </text>
            <text x="1194" y="254" fill={record ? "#e2e8f0" : "#94a3b8"} fontSize="12" fontWeight="600">
              Evidence event
            </text>
            <text x="1194" y="276" fill="#94a3b8" fontSize="10" fontFamily="ui-monospace, monospace">
              {record?.output.request_id ?? "request ID"}
            </text>
            <text x="1194" y="294" fill="#64748b" fontSize="10">
              {record ? `${record.output.latency_ms} ms simulated` : "auditable output"}
            </text>
          </g>

          <g fill="#64748b" fontSize="10">
            <text x="20" y="500">1 Synthetic transaction</text>
            <text x="220" y="500">2 Validation &amp; idempotency</text>
            <text x="510" y="500">3 Eight signal families</text>
            <text x="845" y="500">4 Transparent score</text>
            <text x="995" y="500">5 Human-review policy</text>
            <text x="1194" y="500">6 Structured audit</text>
          </g>
        </svg>
      </div>
      <p className="border-t border-white/[0.06] px-4 py-2 text-[10px] text-slate-500 sm:hidden">
        Scroll horizontally to inspect the complete transaction flow.
      </p>
    </div>
  );
}

function StageNode({
  x,
  y,
  width,
  height,
  index,
  label,
  active,
  tone,
  children,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  index: string;
  label: string;
  active: boolean;
  tone: "teal" | "violet" | "amber" | "rose";
  children: ReactNode;
}) {
  const colors = {
    teal: { stroke: "#5eead4", fill: "rgba(94,234,212,.055)" },
    violet: { stroke: "#c4b5fd", fill: "rgba(196,181,253,.055)" },
    amber: { stroke: "#f6a83b", fill: "rgba(246,168,59,.055)" },
    rose: { stroke: "#fda4af", fill: "rgba(253,164,175,.065)" },
  };
  const color = colors[tone];
  const center = x + width / 2;

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx="9"
        fill={active ? color.fill : "rgba(15,23,42,.72)"}
        stroke={active ? color.stroke : "rgba(100,116,139,.34)"}
        strokeWidth={active ? "1.5" : "1"}
      />
      <text x={x + 12} y={y + 17} fill="#64748b" fontSize="9" fontWeight="700" letterSpacing="1.2">
        {index}
      </text>
      <text x={center} y={y + 35} fill="#f8fafc" fontSize="13" fontWeight="700" textAnchor="middle">
        {label}
      </text>
      <text x={center} y={y + 35} fill="#94a3b8" fontSize="9.5" textAnchor="middle">
        {children}
      </text>
    </g>
  );
}
