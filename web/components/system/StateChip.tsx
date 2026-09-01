import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Info,
  Loader2,
  MinusCircle,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";

/**
 * The single state vocabulary for decisions, evidence, and pipeline stages.
 *
 * Each state carries an icon and a text label as well as a color, so the state
 * survives greyscale, color-blind viewing, and screen readers.
 */
export type SystemState =
  | "verified"
  | "review"
  | "warning"
  | "critical"
  | "info"
  | "running"
  | "pending"
  | "unavailable";

const ICONS: Record<SystemState, LucideIcon> = {
  verified: CheckCircle2,
  review: AlertTriangle,
  warning: AlertTriangle,
  critical: ShieldAlert,
  info: Info,
  running: Loader2,
  pending: CircleDashed,
  unavailable: MinusCircle,
};

/** Maps a state to the CSS `data-state` bucket defined in `globals.css`. */
function surfaceFor(state: SystemState) {
  if (state === "pending" || state === "unavailable") return "neutral";
  return state;
}

export function StateChip({
  state,
  label,
  className,
}: {
  state: SystemState;
  label: string;
  className?: string;
}) {
  const Icon = ICONS[state];
  return (
    <span
      className={`ss-state${className ? ` ${className}` : ""}`}
      data-state={surfaceFor(state)}
      data-system-state={state}
    >
      <Icon
        className={`h-3.5 w-3.5 shrink-0${
          state === "running" ? " motion-safe:animate-spin" : ""
        }`}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}

export function StateIcon({
  state,
  className,
}: {
  state: SystemState;
  className?: string;
}) {
  const Icon = ICONS[state];
  return <Icon className={className} aria-hidden="true" />;
}
