"use client";

import { DISPLAY_CURRENCIES, ILLUSTRATIVE_INR_PER_USD } from "@/data/displayCurrency";
import { useCommandDisplayCurrency } from "@/components/dashboard/DisplayCurrencyContext";

export function CurrencyContextBar() {
  const context = useCommandDisplayCurrency();
  if (!context) return null;

  return (
    <div className="command-panel flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between" role="group" aria-label="Synthetic and illustrative display currency">
      <p className="max-w-3xl text-[11.5px] leading-5 text-slate-400">
        Currency applies to fabricated synthetic transactions and illustrative cost arithmetic only. Historical Amount remains currency-neutral. INR is the default; USD uses the fixed display-only conversion 1 USD = ₹{ILLUSTRATIVE_INR_PER_USD.toFixed(2)}. No live FX is fetched.
      </p>
      <div className="inline-flex w-fit shrink-0 rounded-md border border-white/10 bg-slate-950/60 p-1" role="radiogroup" aria-label="Command-center display currency">
        {DISPLAY_CURRENCIES.map((currency) => {
          const selected = context.displayCurrency === currency;
          return (
            <button
              key={currency}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => context.setDisplayCurrency(currency)}
              className={`rounded px-3 py-1.5 text-xs font-semibold transition ${selected ? "bg-teal-200 text-slate-950" : "text-slate-400 hover:bg-white/[0.05] hover:text-white"}`}
            >
              {currency}
            </button>
          );
        })}
      </div>
    </div>
  );
}
