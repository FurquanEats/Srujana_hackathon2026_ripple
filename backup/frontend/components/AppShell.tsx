"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { Icon, type IconName } from "./ui";

const NAV: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Live", icon: "activity" },
  { href: "/trace", label: "Trace", icon: "search" },
  { href: "/check", label: "Check", icon: "shield" },
  { href: "/eval", label: "Results", icon: "list" },
];

export const DISCLAIMER =
  "Ripple recommends. Officers decide. Ripple never accuses anyone, never moves money on its own, and runs on synthetic and public data only.";

const isActive = (path: string | null, href: string) =>
  path !== null && (href === "/" ? path === "/" || path.startsWith("/cases") : path.startsWith(href));

/** Three rings spreading from a point: one payment, and everything it touches. */
export function RippleMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <circle cx="16" cy="16" r="3.5" fill="#0b6e63" />
      <circle cx="16" cy="16" r="8.5" fill="none" stroke="#0b6e63" strokeOpacity="0.55" strokeWidth="1.6" />
      <circle cx="16" cy="16" r="13.5" fill="none" stroke="#0b6e63" strokeOpacity="0.22" strokeWidth="1.6" />
    </svg>
  );
}

function Wordmark() {
  return (
    <Link href="/" className="flex min-h-11 items-center gap-2.5 rounded-full pr-2">
      <RippleMark />
      <span className="text-[1.15rem] font-semibold tracking-[-0.03em] text-navy">Ripple</span>
      <span className="hidden text-sm text-subtle lg:inline">Stop the scam. Follow the money.</span>
    </Link>
  );
}

function NavItems({ path, mobile, onNavigate }: { path: string | null; mobile?: boolean; onNavigate?: () => void }) {
  return (
    <ul className={mobile ? "space-y-1 px-4 py-3" : "flex items-center gap-1 rounded-full border border-line bg-surface p-1"}>
      {NAV.map((n) => {
        const active = isActive(path, n.href);
        const base = mobile
          ? "flex min-h-12 items-center gap-3 rounded-xl px-3 text-base font-medium"
          : "inline-flex min-h-9 items-center gap-1.5 rounded-full px-4 text-sm font-medium";
        return (
          <li key={n.href}>
            <Link href={n.href} aria-current={active ? "page" : undefined} onClick={onNavigate}
                  className={`${base} ${active ? "bg-navy text-white" : "text-muted hover:bg-sunken hover:text-ink"}`}>
              {mobile && <Icon name={n.icon} className="h-5 w-5" />}
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
      <a href="#main" className="skip-link rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white shadow-pop">Skip to content</a>
      <header className="no-print sticky top-0 z-40 border-b border-line bg-canvas/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between gap-4 px-4 py-2.5 sm:px-8">
          <Wordmark />
          <nav aria-label="Main" className="hidden md:block">
            <Nav />
          </nav>
          <button type="button" className="inline-flex h-11 w-11 items-center justify-center rounded-full text-ink hover:bg-sunken md:hidden"
                  aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? "Close menu" : "Open menu"}
                  onClick={() => setOpen(!open)}>
            <Icon name={open ? "x" : "menu"} className="h-6 w-6" />
          </button>
        </div>
        <nav id="mobile-nav" aria-label="Main" hidden={!open} className="border-t border-line md:hidden">
          <Nav mobile onNavigate={() => setOpen(false)} />
        </nav>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-8 focus:outline-none sm:px-8 sm:py-12">
        {children}
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-subtle sm:px-8">
          <p className="flex items-center gap-2"><RippleMark className="h-4 w-4" /> {DISCLAIMER}</p>
          <p>Built for Srujana 2026 · F-01</p>
        </div>
      </footer>
    </div>
  );
}
