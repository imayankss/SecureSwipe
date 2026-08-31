import { cn } from "@/lib/utils";

export function Progress({ value, className }: { value: number; className?: string }) {
  const boundedValue = Math.max(0, Math.min(100, value));
  return (
    <div
      className={cn("h-2 overflow-hidden rounded-full bg-white/10", className)}
      role="progressbar"
      aria-label="Hypothetical model score"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={boundedValue}
    >
      <div
        className="h-full rounded-full bg-blue-500"
        style={{ width: `${boundedValue}%` }}
      />
    </div>
  );
}
