import type { ReactNode } from "react";

import type { Tier } from "@/lib/api";

const tierStyle: Record<Tier, string> = {
  Critical: "bg-red-500/15 text-red-300 ring-red-500/40",
  Review: "bg-amber-500/15 text-amber-200 ring-amber-500/40",
  Watch: "bg-slate-500/20 text-slate-300 ring-slate-500/40",
};

export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${tierStyle[tier]}`}>
      {tier}
    </span>
  );
}

export function riskColor(p: number) {
  if (p >= 0.85) return "#f87171";
  if (p >= 0.7) return "#fbbf24";
  if (p >= 0.6) return "#94a3b8";
  return "#334155";
}

export function RiskDot({ p }: { p: number }) {
  return (
    <span
      aria-label={`risk ${(p * 100).toFixed(0)} percent`}
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ background: riskColor(p) }}
    />
  );
}

export function Card({ title, action, children, className = "" }: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-slate-800 bg-slate-900/60 p-4 ${className}`}>
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone = "default" }: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "good" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-red-300" : "text-slate-100";
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: string }) {
  return (
    <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
      {error}
    </p>
  );
}

const layerStyle: Record<string, string> = {
  detector: "bg-red-500/15 text-red-200",
  baseline: "bg-sky-500/15 text-sky-200",
  graph: "bg-violet-500/15 text-violet-200",
  model: "bg-emerald-500/15 text-emerald-200",
};

export function LayerTag({ layer }: { layer: string }) {
  return <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${layerStyle[layer] ?? ""}`}>{layer}</span>;
}
