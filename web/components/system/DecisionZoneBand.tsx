import type { BoundedDecision } from "@/components/system/DecisionBadge";

/**
 * Shows which bounded zone an outcome landed in, relative to the operating
 * threshold.
 *
 * Deliberately zone-based rather than needle-based. The public response
 * contract suppresses the decision score, so plotting the score as a position
 * would leak the same value the contract withholds. Only the threshold — which
 * the API does publish — is positioned.
 */
export function DecisionZoneBand({
  decision,
  operatingThreshold,
  idPrefix = "",
}: {
  decision: BoundedDecision;
  operatingThreshold: number | null;
  idPrefix?: string;
}) {
  const descriptionId = `${idPrefix}zone-description`;
  const belowActive = decision === "below_threshold";
  const reviewActive = decision === "review";
  const thresholdPercent =
    operatingThreshold !== null && operatingThreshold > 0 && operatingThreshold < 1
      ? Math.round(operatingThreshold * 100)
      : 53;

  const summary =
    decision === "review"
      ? "The outcome fell in the review zone, at or above the operating threshold."
      : decision === "below_threshold"
        ? "The outcome fell below the operating threshold, so no review was raised."
        : decision === "unavailable"
          ? "No zone was reached. The request failed closed without an outcome."
          : "No request has been evaluated yet.";

  return (
    <figure className="m-0" data-decision-zone={decision}>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="ss-eyebrow">Bounded decision zone</span>
        {operatingThreshold !== null ? (
          <span className="ss-provenance text-[11px] text-slate-400">
            Operating threshold {operatingThreshold.toFixed(2)}
          </span>
        ) : null}
      </figcaption>

      <div
        className="ss-zone-track mt-2.5"
        style={{
          ["--ss-zone-below" as string]: `${thresholdPercent}fr`,
          ["--ss-zone-review" as string]: `${100 - thresholdPercent}fr`,
        }}
        role="img"
        aria-describedby={descriptionId}
        aria-label={summary}
      >
        <div
          className="ss-zone-cell text-emerald-300"
          data-zone="below"
          data-active={belowActive}
        >
          <p className="text-[11px] font-bold uppercase tracking-[0.08em]">
            Below threshold
          </p>
          <p className="mt-1 text-[11px] leading-4 text-slate-400">No review raised</p>
        </div>
        <div
          className="ss-zone-cell text-amber-300"
          data-zone="review"
          data-active={reviewActive}
        >
          <p className="text-[11px] font-bold uppercase tracking-[0.08em]">
            Review zone
          </p>
          <p className="mt-1 text-[11px] leading-4 text-slate-400">Human reviewer decides</p>
        </div>
      </div>

      <p id={descriptionId} className="mt-2.5 text-xs leading-5 text-slate-400">
        {summary}{" "}
        <span className="text-slate-500">
          The decision score itself is not published by the response contract, so
          this band shows the zone reached rather than a plotted score.
        </span>
      </p>
    </figure>
  );
}
