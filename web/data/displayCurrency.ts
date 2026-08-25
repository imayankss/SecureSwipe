export const DISPLAY_CURRENCIES = ["INR", "USD"] as const;

export type DisplayCurrency = (typeof DISPLAY_CURRENCIES)[number];

export const DEFAULT_DISPLAY_CURRENCY: DisplayCurrency = "INR";

/**
 * Fixed, display-only reference used by the synthetic and illustrative panels.
 * It is deliberately code-defined rather than fetched, and is not live FX,
 * Razorpay economics, or evidence about the historical dataset's amount unit.
 */
export const ILLUSTRATIVE_INR_PER_USD = 83;

const fractionDigits = { minimumFractionDigits: 2, maximumFractionDigits: 2 };

export function formatDisplayAmount(value: number, currency: DisplayCurrency) {
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    ...fractionDigits,
  }).format(value);
}

/** Formats a canonical illustrative INR amount in the selected display currency. */
export function formatIllustrativeInr(
  valueInInr: number,
  currency: DisplayCurrency,
) {
  const displayValue =
    currency === "USD" ? valueInInr / ILLUSTRATIVE_INR_PER_USD : valueInInr;
  return formatDisplayAmount(displayValue, currency);
}

/** Formats a fabricated synthetic INR amount in the selected display currency. */
export function formatSyntheticInr(
  valueInInr: number,
  currency: DisplayCurrency,
) {
  return formatIllustrativeInr(valueInInr, currency);
}

export function toIllustrativeInr(
  displayValue: number,
  currency: DisplayCurrency,
) {
  return currency === "USD"
    ? displayValue * ILLUSTRATIVE_INR_PER_USD
    : displayValue;
}

export function fromIllustrativeInr(
  valueInInr: number,
  currency: DisplayCurrency,
) {
  const displayValue =
    currency === "USD" ? valueInInr / ILLUSTRATIVE_INR_PER_USD : valueInInr;
  return Number(displayValue.toFixed(2));
}
