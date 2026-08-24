
"use client";

import { useEffect, useState, type MouseEvent } from "react";
import { GitBranch, ShieldCheck } from "lucide-react";
import { dashboardData } from "@/data/metrics";

const navItems = [
  ["Overview", "#overview"],
  ["Historical", "#historical"],
  ["Performance", "#performance"],
  ["Thresholds", "#thresholds"],
  ["Explainability", "#shap"],
  ["Demo inference", "#risk"],
  ["Synthetic flow", "#synthetic"],
  ["Cost & workload", "#illustrative-cost"],
  ["Architecture", "#architecture"],
  ["Limitations", "#limitations"],
];

export function Navigation() {
  const [active, setActive] = useState("#overview");

  const skipToMainContent = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    document.getElementById("main-content")?.focus();
  };

  useEffect(() => {
    const targets = navItems
      .map(([, href]) => document.querySelector<HTMLElement>(href))
      .filter((element): element is HTMLElement => Boolean(element));
    if (!targets.length) return;
    const updateActive = () => {
      const marker = window.innerWidth < 1024 ? 160 : 96;
      let current = targets[0];
      let nearestDistance = Number.POSITIVE_INFINITY;
      for (const target of targets) {
        const distance = Math.abs(target.getBoundingClientRect().top - marker);
        if (distance < nearestDistance) {
          current = target;
          nearestDistance = distance;
        }
      }
      setActive(`#${current.id}`);
    };
    updateActive();
    window.addEventListener("scroll", updateActive, { passive: true });
    window.addEventListener("resize", updateActive);
    return () => {
      window.removeEventListener("scroll", updateActive);
      window.removeEventListener("resize", updateActive);
    };
  }, []);

  return (
    <>
      <a className="skip-link" href="#main-content" onClick={skipToMainContent}>
        Skip to main content
      </a>
      <header className="sticky top-0 z-50 border-b border-white/[0.08] bg-[#07111f]/92 backdrop-blur-xl">
        <nav
          className="command-nav mx-auto flex max-w-[1280px] flex-wrap items-center gap-2 px-4 py-2.5 sm:px-6"
          aria-label="Primary navigation"
        >
        <a href="#overview" className="flex shrink-0 items-center gap-2 rounded-md font-semibold text-white">
          <span className="grid h-7 w-7 place-items-center rounded-md border border-teal-200/25 bg-teal-300/10">
            <ShieldCheck className="h-4 w-4 text-teal-200" aria-hidden="true" />
          </span>
          <span className="leading-tight">
            <span className="block text-[13.5px]">SecureSwipe</span>
            <span className="block text-[9px] font-medium uppercase tracking-[0.12em] text-slate-500">AI Risk Manager</span>
          </span>
        </a>
        <div className="command-nav-scroller min-w-0 flex-1 overflow-x-auto">
          <div className="flex w-max items-center gap-1 rounded-md border border-white/[0.07] bg-white/[0.025] p-1 text-slate-300">
          {navItems.map(([label, href]) => (
            <a
              key={href}
              aria-current={active === href ? "true" : undefined}
              className={`whitespace-nowrap rounded px-2.5 py-1.5 text-[11.5px] transition ${active === href ? "bg-white/[0.08] font-semibold text-white" : "hover:bg-white/[0.05] hover:text-teal-100"}`}
              href={href}
            >
              {label}
            </a>
          ))}
          </div>
        </div>
        <details className="relative ml-auto lg:hidden">
          <summary className="cursor-pointer list-none rounded-md border border-white/15 px-2.5 py-2 text-xs font-medium text-white marker:content-none">
            Sections
          </summary>
          <div className="absolute right-0 mt-2 grid max-h-[70vh] min-w-52 gap-1 overflow-y-auto rounded-md border border-white/15 bg-slate-950 p-2 shadow-xl">
            {navItems.map(([label, href]) => (
              <a
                key={href}
                className="rounded-md px-3 py-2 text-xs text-slate-200 hover:bg-white/[0.08] hover:text-cyan-100"
                href={href}
              >
                {label}
              </a>
            ))}
          </div>
        </details>
        <a
          href={dashboardData.project.repository}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex shrink-0 items-center gap-2 rounded-md border border-white/15 px-2.5 py-2 text-xs font-medium text-white transition hover:border-teal-200/30 hover:bg-white/[0.06]"
          aria-label="Open SecureSwipe GitHub repository"
        >
          <GitBranch className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">GitHub</span>
        </a>
        </nav>
      </header>
    </>
  );
}
