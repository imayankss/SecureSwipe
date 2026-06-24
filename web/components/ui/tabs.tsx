import * as React from "react";
import { cn } from "@/lib/utils";

export function Tabs({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("rounded-lg border border-white/10 bg-white/[0.03]", className)} {...props} />;
}
