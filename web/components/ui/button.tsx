import * as React from "react";
import { cn } from "@/lib/utils";

type ButtonProps = React.ComponentProps<"a"> & {
  variant?: "primary" | "secondary";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <a
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition duration-200 focus:outline-none focus:ring-2 focus:ring-teal-200/60",
        variant === "primary"
          ? "bg-[#f6b44a] text-[#16100a] hover:bg-[#f8c56c]"
          : "border border-white/15 bg-white/[0.04] text-white hover:border-teal-200/30 hover:bg-white/[0.08]",
        className,
      )}
      {...props}
    />
  );
}
