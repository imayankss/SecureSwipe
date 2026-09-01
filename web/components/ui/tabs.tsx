import * as React from "react";
import { cn } from "@/lib/utils";

export function Tabs({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("rounded-xl border border-[var(--ss-border)] bg-[var(--ss-surface)]", className)} {...props} />;
}
