import * as React from "react";
import { cn } from "@/lib/utils";

type ButtonProps = React.ComponentProps<"a"> & {
  variant?: "primary" | "secondary";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <a
      className={cn(
        "inline-flex h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition duration-200 hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-cyan-200/40",
        variant === "primary"
          ? "bg-cyan-300 text-slate-950 hover:bg-cyan-200"
          : "border border-white/15 bg-white/[0.04] text-white hover:bg-white/[0.09]",
        className,
      )}
      {...props}
    />
  );
}
