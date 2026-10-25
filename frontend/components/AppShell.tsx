"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { Icon, type IconName } from "./ui";

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Command centre", icon: "activity" },
  { href: "/trace", label: "Report a scam", icon: "search" },
  { href: "/check", label: "Check a payment", icon: "shield" },
  { href: "/eval", label: "Evaluation", icon: "list" },
];

export const DISCLAIMER =
  "Risk indicators and drafts for a human officer to review. Ripple does not decide that anyone committed fraud, does not file reports and uses only synthetic and public data.";

const isActive = (path: string | null, href: string) =>
  path !== null && (href === "/" ? path === "/" || path.startsWith("/cases") : path.startsWith(href));

function Wordmark() {
  return (
    <Link href="/" className="flex min-h-11 items-center gap-2.5 rounded-md text-white">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
        <circle cx="16" cy="16" r="4" fill="#5fd0d9" />
        <circle cx="16" cy="16" r="9" fill="none" stroke="#5fd0d9" strokeOpacity="0.7" strokeWidth="2" />
        <circle cx="16" cy="16" r="14" fill="none" stroke="#5fd0d9" strokeOpacity="0.35" strokeWidth="2" />
      </svg>
      <span className="text-lg font-semibold tracking-tight">Ripple</span>
      <span className="hidden border-l border-navy-700 pl-2.5 text-xs text-navy-300 lg:inline">Fraud &amp; mule-account investigation</span>
    </Link>
  );
}

function NavItems({ path, mobile, onNavigate }: { path: string | null; mobile?: boolean; onNavigate?: () => void }) {
  return (
    <ul className={mobile ? "space-y-1 px-4 py-3" : "flex items-center gap-1"}>
      {NAV.map((n) => {
        const active = isActive(path, n.href);
        const base = mobile
          ? "flex min-h-12 items-center gap-3 rounded-md px-3 text-base font-medium"
          : "inline-flex min-h-11 items-center gap-2 rounded-md px-3 text-sm font-medium";
        return (
          <li key={n.href}>
            <Link href={n.href} aria-current={active ? "page" : undefined} onClick={onNavigate}
                  className={`${base} ${active ? "bg-navy-700 text-white" : "text-navy-300 hover:bg-navy-800 hover:text-white"}`}>
              <Icon name={n.icon} className={mobile ? "h-5 w-5" : "h-4 w-4"} />
              {n.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/** Reads the current route, so it renders inside Suspense; the fallback is the same menu without the active marker. */
function RoutedNavItems(props: { mobile?: boolean; onNavigate?: () => void }) {
  return <NavItems path={usePathname()} {...props} />;
}

function Nav(props: { mobile?: boolean; onNavigate?: () => void }) {
  return (
    <Suspense fallback={<NavItems path={null} {...props} />}>
      <RoutedNavItems {...props} />
    </Suspense>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="flex min-h-full flex-col">
      <a href="#main" className="skip-link rounded-md bg-surface px-3 py-2 text-sm font-semibold text-navy shadow-pop">Skip to content</a>
      <header className="no-print sticky top-0 z-40 bg-navy text-white">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-4 py-2 sm:px-6">
          <Wordmark />
          <nav aria-label="Main" className="hidden md:block">
            <Nav />
          </nav>
          <button type="button" className="inline-flex h-11 w-11 items-center justify-center rounded-md text-white hover:bg-navy-800 md:hidden"
                  aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? "Close menu" : "Open menu"}
                  onClick={() => setOpen(!open)}>
            <Icon name={open ? "x" : "menu"} className="h-6 w-6" />
          </button>
        </div>
        <nav id="mobile-nav" aria-label="Main" hidden={!open} className="border-t border-navy-700 md:hidden">
          <Nav mobile onNavigate={() => setOpen(false)} />
        </nav>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 focus:outline-none sm:px-6 sm:py-8">
        {children}
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-[1440px] items-start gap-2.5 px-4 py-5 text-sm text-muted sm:px-6">
          <Icon name="shield" className="mt-0.5 h-4 w-4 text-teal" />
          <p>{DISCLAIMER}</p>
        </div>
      </footer>
    </div>
  );
}
