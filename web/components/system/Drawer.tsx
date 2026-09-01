"use client";

import { useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A modal side drawer with complete keyboard semantics.
 *
 * Focus moves in on open, is trapped while open, Escape closes, and focus
 * returns to whatever opened it.
 *
 * Rendered through a portal to `document.body`. The route's `<main>` uses
 * `overflow-x: clip`, and an ancestor clip region clips fixed descendants even
 * though their containing block is the viewport — which silently cut the
 * drawer's header off the top of the screen. The portal escapes that clip
 * context; `aria-modal` and `aria-labelledby` carry the semantics instead of
 * DOM ancestry.
 */
export function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  labelledBy,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  labelledBy: string;
}) {
  const panel = useRef<HTMLDivElement | null>(null);
  const restoreTo = useRef<HTMLElement | null>(null);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const targets = Array.from(
        panel.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((node) => node.offsetParent !== null || node === document.activeElement);
      if (targets.length === 0) {
        event.preventDefault();
        return;
      }
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    restoreTo.current = document.activeElement as HTMLElement | null;
    const firstFocusable = panel.current?.querySelector<HTMLElement>(FOCUSABLE);
    (firstFocusable ?? panel.current)?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      restoreTo.current?.focus();
    };
  }, [open]);

  // `open` only becomes true from a client interaction, so the portal never
  // runs during server rendering. The document guard covers the case of a
  // parent that renders this already open.
  if (!open || typeof document === "undefined") return null;

  const describedBy = description ? `${labelledBy}-description` : undefined;

  return createPortal(
    <>
      <div className="ss-scrim" onClick={onClose} aria-hidden="true" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className="ss-drawer focus:outline-none"
      >
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[var(--ss-border)] p-4 sm:p-5">
          <div className="min-w-0">
            <h2 id={labelledBy} className="text-base font-semibold text-white">
              {title}
            </h2>
            {description ? (
              <p id={describedBy} className="mt-1.5 text-xs leading-5 text-slate-400">
                {description}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ss-chip min-h-0 shrink-0 px-2 py-1.5 focus:outline-none"
          >
            <X className="h-4 w-4" aria-hidden="true" />
            Close
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">{children}</div>
      </div>
    </>,
    document.body,
  );
}
