import * as React from "react";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.ComponentProps<"span">) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-blue-400/35 bg-blue-500/10 px-2.5 py-1 text-xs font-semibold tracking-[0.01em] text-blue-100",
        className,
      )}
      {...props}
    />
  );
}
