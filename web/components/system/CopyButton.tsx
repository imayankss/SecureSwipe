"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

/**
 * Copies a short reference to the clipboard and announces the result.
 *
 * Falls back to a visible "copy unavailable" state rather than failing
 * silently, because a reviewer needs to know the reference was not captured.
 */
export function CopyButton({
  value,
  label,
  className,
}: {
  value: string;
  label: string;
  className?: string;
}) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    window.clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(value);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
    timer.current = window.setTimeout(() => setStatus("idle"), 2200);
  }

  return (
    <>
      <button
        type="button"
        onClick={copy}
        className={`ss-chip min-h-0 px-2.5 py-1.5 text-[11px] focus:outline-none${
          className ? ` ${className}` : ""
        }`}
      >
        {status === "copied" ? (
          <Check className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {label}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {status === "copied"
          ? `${label}: copied to clipboard.`
          : status === "failed"
            ? `${label}: copying is unavailable in this browser.`
            : ""}
      </span>
    </>
  );
}
