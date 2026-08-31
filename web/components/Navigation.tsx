import Link from "next/link";
import { ShieldCheck } from "lucide-react";

import { dashboardData } from "@/data/metrics";

const navItems = [
  ["Overview", "/", "product"],
  ["Evidence", "/evidence", "evidence"],
  ["Demo", "/demo", "demo"],
] as const;

type NavigationProps = {
  activePage: "product" | "evidence" | "demo";
};

function GitHubMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.64 0 8.13c0 3.59 2.29 6.64 5.47 7.71.4.08.55-.17.55-.39 0-.19-.01-.83-.01-1.51-2.01.38-2.53-.5-2.69-.96-.09-.23-.48-.96-.82-1.15-.28-.15-.68-.53-.01-.54.63-.01 1.08.59 1.23.83.72 1.23 1.87.88 2.33.67.07-.53.28-.88.51-1.08-1.78-.21-3.64-.91-3.64-4.02 0-.89.31-1.62.82-2.19-.08-.21-.36-1.04.08-2.16 0 0 .67-.22 2.2.84A7.4 7.4 0 0 1 8 3.91c.68 0 1.36.09 2 .27 1.53-1.06 2.2-.84 2.2-.84.44 1.12.16 1.95.08 2.16.51.57.82 1.29.82 2.19 0 3.12-1.87 3.81-3.65 4.02.29.25.54.74.54 1.51 0 1.09-.01 1.97-.01 2.24 0 .22.15.47.55.39A8.15 8.15 0 0 0 16 8.13C16 3.64 12.42 0 8 0Z" />
    </svg>
  );
}

export function Navigation({ activePage }: NavigationProps) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="ss-site-header sticky top-0 z-50">
        <nav
          className="command-nav ss-page-shell flex flex-wrap items-center gap-2 py-2.5"
          aria-label="Primary navigation"
        >
          <Link
            href="/"
            prefetch={false}
            className="flex min-h-11 shrink-0 items-center gap-2 rounded-lg font-semibold text-white focus:outline-none"
            aria-label="SecureSwipe product overview"
          >
            <span className="ss-icon-tile h-8 w-8">
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="leading-tight">
              <span className="block text-base tracking-[-0.01em]">SecureSwipe</span>
              <span className="block text-[9px] font-medium uppercase tracking-[0.12em] text-slate-500">
                AI Risk Manager
              </span>
            </span>
          </Link>

          <div className="command-nav-scroller hidden min-w-0 flex-1 sm:block">
            <div className="ss-nav-group flex w-max items-center gap-1">
              {navItems.map(([label, href, page]) => (
                <Link
                  key={href}
                  prefetch={false}
                  aria-current={activePage === page ? "page" : undefined}
                  className="ss-nav-item whitespace-nowrap focus:outline-none"
                  href={href}
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>

          <details className="relative sm:hidden">
            <summary className="ss-chip cursor-pointer list-none marker:content-none focus:outline-none">
              Pages
            </summary>
            <div className="ss-mobile-menu absolute right-0 mt-2 grid min-w-44 gap-1 p-2">
              {navItems.map(([label, href, page]) => (
                <Link
                  key={href}
                  prefetch={false}
                  aria-current={activePage === page ? "page" : undefined}
                  className="ss-nav-item min-h-11 focus:outline-none"
                  href={href}
                >
                  {label}
                </Link>
              ))}
            </div>
          </details>

          <a
            href={dashboardData.project.repository}
            target="_blank"
            rel="noopener noreferrer"
            className="ss-action ss-action-secondary ml-auto h-11 w-11 shrink-0 p-0 focus:outline-none"
            aria-label="Open SecureSwipe GitHub repository"
            title="GitHub repository"
          >
            <GitHubMark className="h-7 w-7" />
          </a>
        </nav>
      </header>
    </>
  );
}
