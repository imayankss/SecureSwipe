import { Card, CardContent } from "@/components/ui/card";

export function MetricCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description?: string;
}) {
  return (
    <Card className="min-h-28 bg-[linear-gradient(145deg,rgba(18,35,54,0.96),rgba(12,25,42,0.9))]">
      <CardContent className="p-4">
        <p className="ss-eyebrow text-[0.64rem] text-slate-400">{label}</p>
        <p className="ss-number mt-3 text-2xl font-semibold text-white sm:text-3xl">{value}</p>
        {description ? <p className="mt-2 text-sm leading-5 text-slate-300">{description}</p> : null}
      </CardContent>
    </Card>
  );
}
