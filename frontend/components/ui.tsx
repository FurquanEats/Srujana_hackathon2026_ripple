"use client";

import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import type { Tier } from "@/lib/api";
import { LAYER_LABEL } from "@/lib/labels";

/* ------------------------------------------------------------------ icons */

const ICONS = {
  critical: ["M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z", "M12 9v4", "M12 17h.01"],
  review: ["M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z", "M12 8v4", "M12 16h.01"],
  watch: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"],
  info: ["M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z", "M12 16v-4", "M12 8h.01"],
  check: ["M20 6 9 17l-5-5"],
  x: ["M18 6 6 18", "M6 6l12 12"],
  menu: ["M4 6h16", "M4 12h16", "M4 18h16"],
  copy: ["M11 9h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2Z", "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"],
  play: ["M7 4.5v15l12-7.5-12-7.5Z"],
  pause: ["M8 5v14", "M16 5v14"],
  back: ["M18 19 9 12l9-7v14Z", "M6 5v14"],
  forward: ["M6 5l9 7-9 7V5Z", "M18 5v14"],
  arrowRight: ["M5 12h14", "M13 6l6 6-6 6"],
  arrowLeft: ["M19 12H5", "M11 6l-6 6 6 6"],
  chevron: ["M6 9l6 6 6-6"],
  draft: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z", "M14 2v6h6", "M16 13H8", "M16 17H8"],
  shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"],
  search: ["M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16Z", "m21 21-4.3-4.3"],
  flask: ["M9 3h6", "M10 3v6l-5.6 9.6A2 2 0 0 0 6.1 21.5h11.8a2 2 0 0 0 1.7-2.9L14 9V3", "M7 15h10"],
  printer: ["M6 9V3h12v6", "M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2", "M6 14h12v7H6z"],
  clock: ["M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Z", "M12 6v6l4 2"],
  lock: ["M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z", "M7 11V7a5 5 0 0 1 10 0v4"],
  activity: ["M22 12h-4l-3 9L9 3l-3 9H2"],
  graph: ["M5 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z", "M19 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z", "M5 22a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z", "M6.7 5.1 17.3 10", "M6.7 18.9 17.3 14"],
  list: ["M8 6h13", "M8 12h13", "M8 18h13", "M3 6h.01", "M3 12h.01", "M3 18h.01"],
  wifiOff: ["M2 2l20 20", "M8.5 16.4a5 5 0 0 1 7 0", "M5 12.9a10 10 0 0 1 5.2-2.8", "M12 20h.01", "M19 12.9a10 10 0 0 0-2.2-1.6", "M2 8.8a15 15 0 0 1 4.2-2.7", "M22 8.8A15 15 0 0 0 10.7 5"],
} as const;

export type IconName = keyof typeof ICONS;

export function Icon({ name, className = "h-4 w-4", label }: { name: IconName; className?: string; label?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
         className={`shrink-0 ${className}`} aria-hidden={label ? undefined : true} role={label ? "img" : undefined} aria-label={label}>
      {ICONS[name].map((d) => <path key={d} d={d} />)}
    </svg>
  );
}

/* ------------------------------------------------------------------ severity */

const tierStyle: Record<Tier, { cls: string; icon: IconName }> = {
  Critical: { cls: "bg-critical text-white ring-critical", icon: "critical" },
  Review: { cls: "bg-review-soft text-review ring-review-line", icon: "review" },
  Watch: { cls: "bg-watch-soft text-watch ring-line", icon: "watch" },
};

/** Severity is carried by icon shape and the word itself, never by colour alone. */
export function TierBadge({ tier, size = "md" }: { tier: Tier; size?: "sm" | "md" }) {
  const s = tierStyle[tier];
  const pad = size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-0.5 text-xs";
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md font-semibold ring-1 ring-inset ${pad} ${s.cls}`}>
      <Icon name={s.icon} className="h-3.5 w-3.5" />
      {tier}
    </span>
  );
}

/** Thresholds mirror backend/ripple/packs/india.yaml tiers (alert 0.60, review 0.70, critical 0.85). */
export function riskColor(p: number) {
  if (p >= 0.85) return "#b42332";
  if (p >= 0.7) return "#c87a12";
  if (p >= 0.6) return "#7d8ca1";
  return "#c5d1de";
}

export function RiskDot({ p }: { p: number }) {
  return (
    <span aria-hidden className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: riskColor(p) }} />
  );
}

const layerStyle: Record<string, string> = {
  detector: "bg-navy text-white",
  baseline: "bg-mist text-navy-700",
  graph: "bg-teal-soft text-teal-strong",
  model: "bg-sunken text-muted ring-1 ring-inset ring-line",
};

export function LayerTag({ layer }: { layer: string }) {
  return (
    <span className={`inline-flex whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-semibold ${layerStyle[layer] ?? "bg-sunken text-muted"}`}>
      {LAYER_LABEL[layer] ?? layer}
    </span>
  );
}

/* ------------------------------------------------------------------ surfaces */

export function Card({ title, description, action, children, className = "", id, padded = true }: {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
  padded?: boolean;
}) {
  const headingId = useId();
  return (
    <section id={id} aria-labelledby={title ? headingId : undefined}
             className={`print-break-avoid min-w-0 rounded-card border border-line bg-surface shadow-card ${padded ? "p-4 sm:p-5" : ""} ${className}`}>
      {(title || action) && (
        <header className={`flex flex-wrap items-start justify-between gap-x-4 gap-y-2 ${padded ? "mb-4" : "px-4 pt-4 pb-3 sm:px-5"}`}>
          <div className="min-w-0">
            {title && <h2 id={headingId} className="text-base font-semibold text-navy">{title}</h2>}
            {description && <div className="mt-0.5 text-sm text-muted">{description}</div>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

type Tone = "default" | "good" | "bad" | "accent";
const toneText: Record<Tone, string> = {
  default: "text-ink",
  good: "text-recover",
  bad: "text-critical",
  accent: "text-teal-strong",
};

/** KPI tile. `value` is the figure; `hint` gives the comparison or unit so the number never stands alone. */
export function Stat({ label, value, hint, tone = "default", icon, emphasis = false }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  icon?: IconName;
  emphasis?: boolean;
}) {
  return (
    <div className={`print-break-avoid min-w-0 rounded-card border bg-surface px-4 py-3 shadow-card ${emphasis ? "border-line-strong" : "border-line"}`}>
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
        {icon && <Icon name={icon} className="h-3.5 w-3.5 text-subtle" />}
        <span>{label}</span>
      </div>
      <div className={`mt-1 break-words font-semibold tabular-nums leading-tight ${emphasis ? "text-3xl" : "text-2xl"} ${toneText[tone]}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-subtle">{hint}</div>}
    </div>
  );
}
export const KpiTile = Stat;

/* ------------------------------------------------------------------ feedback */

const noticeStyle = {
  info: { cls: "border-line bg-mist text-navy-700", icon: "info" as IconName },
  success: { cls: "border-[#9fd2bd] bg-recover-soft text-recover", icon: "check" as IconName },
  warning: { cls: "border-review-line bg-review-soft text-review", icon: "review" as IconName },
  error: { cls: "border-critical-line bg-critical-soft text-critical", icon: "critical" as IconName },
};

export function Notice({ tone = "info", title, children, action, className = "" }: {
  tone?: keyof typeof noticeStyle;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const s = noticeStyle[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"}
         className={`flex items-start gap-3 rounded-lg border p-3 text-sm ${s.cls} ${className}`}>
      <Icon name={s.icon} className="mt-0.5 h-4 w-4" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ error, title = "Something went wrong", onRetry }: { error: string; title?: string; onRetry?: () => void }) {
  return (
    <Notice tone="error" title={title}
            action={onRetry && <Button variant="secondary" size="sm" onClick={onRetry}>Try again</Button>}>
      {error}
    </Notice>
  );
}

export function EmptyState({ icon = "info", title, children }: { icon?: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line-strong bg-canvas px-4 py-8 text-center">
      <Icon name={icon} className="h-6 w-6 text-subtle" />
      <p className="mt-2 text-sm font-semibold text-ink">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <span aria-hidden className={`block animate-pulse rounded bg-sunken ${className}`} />;
}

export function LoadingPanel({ label }: { label: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-4">
      <span className="sr-only">{label}</span>
      <Skeleton className="h-8 w-64" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full" />)}
      </div>
      <Skeleton className="h-64 w-full" />
      <p className="text-sm text-muted">{label}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ controls */

const buttonVariant = {
  primary: "bg-teal text-white hover:bg-teal-strong border border-teal",
  navy: "bg-navy text-white hover:bg-navy-800 border border-navy",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-sunken",
  ghost: "bg-transparent text-ink border border-transparent hover:bg-sunken",
  danger: "bg-critical text-white border border-critical hover:bg-[#951c29]",
};
const buttonSize = {
  sm: "min-h-9 px-3 text-sm gap-1.5",
  md: "min-h-11 px-4 text-sm gap-2",
  lg: "min-h-12 px-5 text-base gap-2",
};

export function Button({ variant = "secondary", size = "md", className = "", children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof buttonVariant; size?: keyof typeof buttonSize }) {
  return (
    <button type="button" {...rest}
            className={`inline-flex items-center justify-center whitespace-nowrap rounded-md font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${buttonVariant[variant]} ${buttonSize[size]} ${className}`}>
      {children}
    </button>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <span aria-hidden className={`inline-block animate-spin rounded-full border-2 border-current border-r-transparent ${className}`} />;
}

/** Labelled form field. The label, hint and error are wired to the control with ids so screen readers announce them. */
export function Field({ label, hint, error, optional, children, className = "" }: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
  className?: string;
  children: (props: { id: string; "aria-describedby"?: string; "aria-invalid"?: boolean }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`min-w-0 ${className}`}>
      <label htmlFor={id} className="flex items-baseline gap-2 text-sm font-semibold text-ink">
        {label}
        {optional && <span className="text-xs font-normal text-subtle">Optional</span>}
      </label>
      <div className="mt-1.5">{children({ id, "aria-describedby": describedBy, "aria-invalid": error ? true : undefined })}</div>
      {error ? (
        <p id={errorId} className="mt-1.5 flex items-center gap-1 text-sm text-critical">
          <Icon name="critical" className="h-3.5 w-3.5" />{error}
        </p>
      ) : hint ? (
        <p id={hintId} className="mt-1.5 text-xs text-subtle">{hint}</p>
      ) : null}
    </div>
  );
}

export const inputClass =
  "block w-full min-h-11 rounded-md border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-subtle " +
  "aria-[invalid=true]:border-critical aria-[invalid=true]:ring-1 aria-[invalid=true]:ring-critical sm:text-sm";

/**
 * Modal dialog on the native <dialog> element: the browser traps focus, closes on Escape and returns focus to the
 * control that opened it.
 */
export function Dialog({ open, onClose, title, description, children, footer, size = "md" }: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: "md" | "lg";
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog ref={ref} aria-labelledby={titleId} aria-describedby={description ? descId : undefined}
            onClose={onClose} onCancel={(e) => { e.preventDefault(); onClose(); }}
            onClick={(e) => { if (e.target === ref.current) onClose(); }}
            className={`m-auto w-[calc(100%-2rem)] ${size === "lg" ? "max-w-2xl" : "max-w-lg"} rounded-xl border border-line bg-surface p-0 text-ink shadow-pop backdrop:bg-navy/50`}>
      {open && (
        <div className="flex max-h-[85vh] flex-col">
          <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <h2 id={titleId} className="text-lg font-semibold text-navy">{title}</h2>
              {description && <p id={descId} className="mt-1 text-sm text-muted">{description}</p>}
            </div>
            <button type="button" onClick={onClose} aria-label="Close dialog"
                    className="-mr-2 -mt-1 inline-flex h-11 w-11 items-center justify-center rounded-md text-muted hover:bg-sunken">
              <Icon name="x" className="h-5 w-5" />
            </button>
          </header>
          <div className="min-h-0 overflow-y-auto px-5 py-4">{children}</div>
          {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line bg-canvas px-5 py-3">{footer}</footer>}
        </div>
      )}
    </dialog>
  );
}

/** Marks synthetic demonstration values and controls so they are never mistaken for live bank data. */
export function DemoBadge({ children = "Demo" }: { children?: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-md border border-dashed border-line-strong bg-canvas px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-muted">
      <Icon name="flask" className="h-3 w-3" />{children}
    </span>
  );
}

export function ConnectionStatus({ connected, warmingUp, updatedAt }: { connected: boolean; warmingUp?: boolean; updatedAt?: Date | null }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm" role="status" aria-live="polite">
      {connected ? (
        <span className="inline-flex items-center gap-2 rounded-full border border-[#9fd2bd] bg-recover-soft px-3 py-1 font-semibold text-recover">
          <span className="relative flex h-2 w-2" aria-hidden>
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-recover opacity-60 motion-reduce:hidden" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-recover" />
          </span>
          Live{warmingUp ? " · warming up" : ""}
        </span>
      ) : (
        <span className="inline-flex items-center gap-2 rounded-full border border-critical-line bg-critical-soft px-3 py-1 font-semibold text-critical">
          <Icon name="wifiOff" className="h-3.5 w-3.5" /> Disconnected · retrying
        </span>
      )}
      <span className="text-xs text-subtle">
        {updatedAt ? <>Updated <time dateTime={updatedAt.toISOString()}>{updatedAt.toLocaleTimeString("en-IN")}</time></> : "No data received yet"}
      </span>
    </div>
  );
}

/** Small "show N more" disclosure used for long evidence lists and account lists. */
export function ShowMore({ expanded, hidden, onToggle, noun, controls }: {
  expanded: boolean;
  hidden: number;
  onToggle: () => void;
  noun: string;
  controls?: string;
}) {
  if (hidden <= 0) return null;
  return (
    <button type="button" onClick={onToggle} aria-expanded={expanded} aria-controls={controls}
            className="mt-3 inline-flex min-h-9 items-center gap-1.5 rounded-md px-2 text-sm font-semibold text-link hover:bg-mist">
      <Icon name="chevron" className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
      {expanded ? "Show fewer" : `Show ${hidden} more ${noun}`}
    </button>
  );
}

export function PageHeader({ title, description, eyebrow, actions }: {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-sm">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-navy sm:text-[1.75rem]">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-muted sm:text-base">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
