"use client";

import { createContext, type ReactNode, useContext, useMemo, useState } from "react";

import { DEFAULT_DISPLAY_CURRENCY, type DisplayCurrency } from "@/data/displayCurrency";

type DisplayCurrencyState = {
  displayCurrency: DisplayCurrency;
  setDisplayCurrency: (currency: DisplayCurrency) => void;
};

const DisplayCurrencyContext = createContext<DisplayCurrencyState | null>(null);

export function DisplayCurrencyProvider({ children }: { children: ReactNode }) {
  const [displayCurrency, setDisplayCurrency] = useState<DisplayCurrency>(DEFAULT_DISPLAY_CURRENCY);
  const value = useMemo(() => ({ displayCurrency, setDisplayCurrency }), [displayCurrency]);
  return <DisplayCurrencyContext.Provider value={value}>{children}</DisplayCurrencyContext.Provider>;
}

export function useCommandDisplayCurrency() {
  return useContext(DisplayCurrencyContext);
}

