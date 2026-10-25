"use client";

import { useState } from "react";

import { money, pct, type AccountProfile, type Reason, type ShapValue } from "@/lib/api";
import { isContextSignal, reasonLabel } from "@/lib/labels";

import { Icon, LayerTag, ShowMore } from "./ui";

const TOP_REASONS = 3;
const TXN_PREVIEW = 4;

function TxnIds({ ids }: { ids: string[] }) {
  const [all, setAll] = useState(false);
  if (ids.length === 0) return null;
  const shown = all ? ids : ids.slice(0, TXN_PREVIEW);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1">
      <span className="mr-1 text-xs text-subtle">Transactions</span>
      {shown.map((id) => (
        <code key={id} className="whitespace-nowrap rounded bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-ink">{id}</code>
      ))}
      {ids.length > TXN_PREVIEW && (
        <button type="button" onClick={() => setAll((a) => !a)} aria-expanded={all}
                className="min-h-7 rounded px-1.5 text-xs font-semibold text-link hover:bg-mist">
          {all ? "fewer" : `+${ids.length - TXN_PREVIEW} more`}
        </button>
      )}
    </div>
  );
}

/** One evidence sentence: what the engine saw, the payments behind it, and what would have made it not fire. */
export function EvidenceStatement({ reason }: { reason: Reason }) {
  const context = isContextSignal(reason.code);
  return (
    <li className="rounded-lg border border-line p-3 sm:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <LayerTag layer={reason.layer} />
        <span className="text-sm font-semibold text-ink">{reasonLabel(reason.code)}</span>
        {context && <span className="text-xs text-subtle">context signal</span>}
        <span className="ml-auto flex items-center gap-2 text-xs text-muted">
          <span className="sr-only">Signal strength</span>
          <span aria-hidden className="h-1.5 w-16 overflow-hidden rounded-full bg-sunken">
            <span className="block h-full rounded-full bg-navy-700" style={{ width: pct(reason.strength) }} />
          </span>
          <span className="tabular-nums">{pct(reason.strength)} strength</span>
        </span>
      </div>
      <p className="mt-2 text-[15px] leading-relaxed text-ink">{reason.text}</p>
      <TxnIds ids={reason.txn_ids} />
      {reason.counterfactual && (
        <p className="mt-2 flex items-start gap-2 rounded-md bg-canvas px-2.5 py-2 text-sm text-muted">
          <Icon name="info" className="mt-0.5 h-4 w-4 text-subtle" />
          <span><span className="font-semibold text-ink">Counterfactual: </span>{reason.counterfactual}</span>
        </p>
      )}
    </li>
  );
}

export function EvidenceList({ reasons }: { reasons: Reason[] }) {
  const [all, setAll] = useState(false);
  if (reasons.length === 0) return <p className="text-sm text-muted">No reasons were recorded for this case.</p>;
  const sorted = [...reasons].sort((a, b) => b.strength - a.strength);
  const shown = all ? sorted : sorted.slice(0, TOP_REASONS);
  return (
    <div>
      <ul id="evidence-list" className="space-y-3">
        {shown.map((r, i) => <EvidenceStatement key={`${r.code}-${i}`} reason={r} />)}
      </ul>
      <ShowMore expanded={all} hidden={sorted.length - TOP_REASONS} onToggle={() => setAll((a) => !a)} noun="reasons" controls="evidence-list" />
    </div>
  );
}

export function ModelContributions({ shap }: { shap: ShapValue[] }) {
  if (shap.length === 0) return null;
  const max = Math.max(...shap.map((s) => Math.abs(s.contribution)), 0.01);
  return (
    <details className="group rounded-lg border border-line">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
        <Icon name="chevron" className="h-4 w-4 transition-transform group-open:rotate-180" />
        ML model contributions ({shap.length} features)
      </summary>
      <div className="border-t border-line px-3 py-3">
        <p className="mb-2 text-xs text-subtle">SHAP contribution in log-odds. Positive pushes the score up; negative pulls it down.</p>
        <ul className="space-y-1.5">
          {shap.map((s) => (
            <li key={s.feature} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 text-xs sm:grid-cols-[14rem_minmax(0,1fr)_4rem]">
              <span className="truncate font-mono text-muted" title={s.feature}>{s.feature} = {s.value}</span>
              <span className="col-span-2 row-start-2 h-2 rounded-full bg-sunken sm:col-span-1 sm:row-start-auto">
                <span className="block h-full rounded-full" style={{ width: `${(Math.abs(s.contribution) / max) * 100}%`, background: s.contribution > 0 ? "#15171a" : "#c2c4c8" }} />
              </span>
              <span className="text-right tabular-nums text-ink">{s.contribution > 0 ? "+" : "−"}{Math.abs(s.contribution).toFixed(2)}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

export function AccountProfiles({ profiles, currency = "INR" }: { profiles: AccountProfile[]; currency?: string }) {
  if (profiles.length === 0) return null;
  return (
    <details className="group rounded-lg border border-line">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 text-sm font-semibold text-ink [&::-webkit-details-marker]:hidden">
        <Icon name="chevron" className="h-4 w-4 transition-transform group-open:rotate-180" />
        Account history ({profiles.length} account{profiles.length === 1 ? "" : "s"})
      </summary>
      <ul className="divide-y divide-line border-t border-line">
        {profiles.map((p) => (
          <li key={p.account_id} className="px-3 py-2.5 text-sm">
            <span className="font-mono font-semibold">{p.account_id}</span>
            {p.persona && <span className="ml-2 text-muted">{p.persona.replace(/_/g, " ")}</span>}
            <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
              {p.opened_days_ago != null && <div><dt className="inline">Opened </dt><dd className="inline font-semibold text-ink">{p.opened_days_ago} days ago</dd></div>}
              {p.median_amount_30d != null && <div><dt className="inline">Median payment (30 days) </dt><dd className="inline font-semibold text-ink">{money(p.median_amount_30d, currency)}</dd></div>}
              {p.txns_30d != null && <div><dt className="inline">Payments (30 days) </dt><dd className="inline font-semibold text-ink">{p.txns_30d}</dd></div>}
              {p.devices.length > 0 && <div><dt className="inline">Devices </dt><dd className="inline font-mono text-ink">{p.devices.join(", ")}</dd></div>}
            </dl>
          </li>
        ))}
      </ul>
    </details>
  );
}
