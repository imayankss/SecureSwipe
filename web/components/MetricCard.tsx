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
    <Card className="min-h-28">
      <CardContent className="p-4">
        <p className="text-xs font-medium uppercase text-slate-400">{label}</p>
        <p className="mt-3 text-2xl font-semibold text-white sm:text-3xl">{value}</p>
        {description ? <p className="mt-2 text-sm leading-5 text-slate-300">{description}</p> : null}
      </CardContent>
    </Card>
  );
}
