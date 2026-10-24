"use client";

import { useState } from "react";

import { money, prob, time, type ScoredTransaction } from "@/lib/api";
import { reasonLabel } from "@/lib/labels";

import { Icon, RiskDot, ShowMore, type IconName } from "./ui";

export interface CaseEvent {
  ts: string;
  title: string;
  detail?: string;
  icon: IconName;
}

type Item = { kind: "txn"; ts: string; txn: ScoredTransaction } | { kind: "event"; ts: string; event: CaseEvent };

const PREVIEW = 8;

/** Payments in the case and the audit-relevant events around them (opened, first alert, decisions), in time order. */
export function Timeline({ transactions, events = [] }: { transactions: ScoredTransaction[]; events?: CaseEvent[] }) {
  const [all, setAll] = useState(false);
  const items: Item[] = [
    ...transactions.map((t) => ({ kind: "txn" as const, ts: t.ts, txn: t })),
    ...events.map((e) => ({ kind: "event" as const, ts: e.ts, event: e })),
  ].sort((a, b) => a.ts.localeCompare(b.ts) || (a.kind === "event" ? 1 : -1));

  if (items.length === 0) return <p className="text-sm text-muted">No events recorded.</p>;
  const shown = all ? items : items.slice(0, PREVIEW);

  return (
    <div>
      <ol id="case-timeline" className="relative space-y-0 border-l-2 border-line pl-0">
        {shown.map((item) => item.kind === "event" ? (
          <li key={`e-${item.event.title}-${item.ts}`} className="relative py-2 pl-6">
            <span className="absolute -left-[11px] top-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-navy text-white">
              <Icon name={item.event.icon} className="h-3 w-3" />
            </span>
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-sm font-semibold text-navy">{item.event.title}</span>
              <time dateTime={item.ts} className="text-xs text-subtle">{time(item.ts)}</time>
            </div>
            {item.event.detail && <p className="text-sm text-muted">{item.event.detail}</p>}
          </li>
        ) : (
          <li key={item.txn.txn_id} className={`relative py-2 pl-6 ${item.txn.is_alert ? "" : "text-muted"}`}>
            <span className="absolute -left-[6px] top-3.5 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-surface ring-2 ring-surface">
              <RiskDot p={item.txn.probability} />
            </span>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                <time dateTime={item.ts} className="text-xs text-subtle">{time(item.ts)}</time>
                <span className="inline-flex flex-wrap items-center gap-1 font-mono text-xs text-ink">
                  {item.txn.src_account}<Icon name="arrowRight" className="h-3 w-3 text-subtle" />{item.txn.dst_account}
                </span>
                {item.txn.is_alert && (
                  <span className="inline-flex items-center gap-1 rounded bg-navy px-1.5 py-0.5 text-[11px] font-semibold text-white">
                    <Icon name="critical" className="h-3 w-3" />Alert · {prob(item.txn.probability)}
                  </span>
                )}
              </div>
              <span className="whitespace-nowrap text-sm font-semibold tabular-nums text-ink">{money(item.txn.amount, item.txn.currency)}</span>
            </div>
            <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-subtle">
              <span className="font-mono">{item.txn.txn_id}</span>
              <span>{item.txn.rail}</span>
              {item.txn.location && <span>{item.txn.location}</span>}
              {item.txn.device_id && <span>device {item.txn.device_id}</span>}
              {item.txn.reasons.length > 0 && <span>{item.txn.reasons.map((r) => reasonLabel(r.code)).join(", ")}</span>}
            </div>
          </li>
        ))}
      </ol>
      <ShowMore expanded={all} hidden={items.length - PREVIEW} onToggle={() => setAll((a) => !a)} noun="events" controls="case-timeline" />
    </div>
  );
}
