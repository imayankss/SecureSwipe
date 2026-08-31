import * as React from "react";
import { cn } from "@/lib/utils";

type ButtonProps = React.ComponentProps<"a"> & {
  variant?: "primary" | "secondary";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  return (
    <a
      className={cn(
        "ss-action focus:outline-none",
        variant === "primary"
          ? "ss-action-primary"
          : "ss-action-secondary",
        className,
      )}
      {...props}
    />
  );
}
