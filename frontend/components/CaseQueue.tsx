import Link from "next/link";

import { money, prob, type CaseSummary } from "@/lib/api";
import { contextOnly, isContextSignal, reasonLabel } from "@/lib/labels";

import { EmptyState, Icon, TierBadge } from "./ui";

/** The signals that put a case in the queue, named as the engine reported them. Context signals are styled quietly. */
export function ReasonChips({ codes, max = 3 }: { codes: string[]; max?: number }) {
  if (codes.length === 0) return <span className="text-xs text-subtle">No signal recorded</span>;
  const shown = codes.slice(0, max);
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((c) => (
        <span key={c}
              className={`whitespace-nowrap rounded px-1.5 py-0.5 text-xs ${isContextSignal(c) ? "border border-dashed border-line-strong text-subtle" : "bg-mist font-medium text-navy-700"}`}>
          {reasonLabel(c)}
        </span>
      ))}
      {codes.length > max && <span className="px-1 py-0.5 text-xs text-subtle">+{codes.length - max} more</span>}
    </span>
  );
}

function rowTone(c: CaseSummary) {
  if (c.tier === "Watch") return "text-muted";
  return "text-ink";
}

function QueueTable({ cases, quiet = false }: { cases: CaseSummary[]; quiet?: boolean }) {
  return (
    <table className="hidden w-full text-left text-sm md:table">
      <thead className={quiet ? "sr-only" : "border-b border-line text-xs text-muted"}>
        <tr>
          <th scope="col" className="py-2 pr-3 font-semibold">Case</th>
          <th scope="col" className="py-2 pr-3 font-semibold">Tier</th>
          <th scope="col" className="py-2 pr-3 text-right font-semibold">Probability</th>
          <th scope="col" className="py-2 pr-3 text-right font-semibold">Money at risk</th>
          <th scope="col" className="py-2 pr-3 text-right font-semibold">Accounts</th>
          <th scope="col" className="py-2 font-semibold">Why it was flagged</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {cases.map((c) => (
          <tr key={c.case_id} className={`group ${rowTone(c)} hover:bg-canvas`}>
            <td className="whitespace-nowrap py-2.5 pr-3">
              <Link href={`/cases/${c.case_id}`} className={`inline-flex min-h-9 items-center gap-1 font-mono font-semibold ${c.tier === "Watch" ? "text-muted" : "text-link"} hover:underline`}>
                {c.case_id}<Icon name="arrowRight" className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100" />
              </Link>
            </td>
            <td className="py-2.5 pr-3"><TierBadge tier={c.tier} size="sm" /></td>
            <td className="whitespace-nowrap py-2.5 pr-3 text-right tabular-nums">{prob(c.probability)}</td>
            <td className={`whitespace-nowrap py-2.5 pr-3 text-right tabular-nums ${c.tier === "Watch" ? "" : "font-semibold"}`}>{money(c.amount_at_risk)}</td>
            <td className="py-2.5 pr-3 text-right tabular-nums">{c.accounts}</td>
            <td className="py-2.5">
              <ReasonChips codes={c.typologies} />
              {c.tier === "Watch" && contextOnly(c.typologies) && (
                <span className="mt-0.5 block text-xs text-subtle">Unusual for this account only; no laundering pattern.</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function QueueCards({ cases }: { cases: CaseSummary[] }) {
  return (
    <ul className="space-y-2 md:hidden">
      {cases.map((c) => (
        <li key={c.case_id}>
          <Link href={`/cases/${c.case_id}`}
                className="block rounded-lg border border-line p-3 hover:bg-canvas">
            <div className="flex items-center justify-between gap-2">
              <span className={`whitespace-nowrap font-mono text-sm font-semibold ${c.tier === "Watch" ? "text-muted" : "text-link"}`}>{c.case_id}</span>
              <TierBadge tier={c.tier} size="sm" />
            </div>
            <dl className={`mt-2 grid grid-cols-3 gap-2 text-sm ${rowTone(c)}`}>
              <div><dt className="text-[11px] text-subtle">Money at risk</dt><dd className="font-semibold tabular-nums">{money(c.amount_at_risk)}</dd></div>
              <div><dt className="text-[11px] text-subtle">Probability</dt><dd className="tabular-nums">{prob(c.probability)}</dd></div>
              <div><dt className="text-[11px] text-subtle">Accounts</dt><dd className="tabular-nums">{c.accounts}</dd></div>
            </dl>
            <div className="mt-2"><ReasonChips codes={c.typologies} /></div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * Case queue in the backend's order (tier, then expected loss). Critical and Review stay in view; Watch cases sit in a
 * quiet, collapsible group so a single weak signal never competes with a live mule chain for attention.
 */
export function CaseQueue({ cases }: { cases: CaseSummary[] }) {
  if (cases.length === 0) {
    return (
      <EmptyState icon="shield" title="No open cases">
        Linked alerts become cases here. In the demo, inject a scenario below to see one appear.
      </EmptyState>
    );
  }
  const urgent = cases.filter((c) => c.tier !== "Watch");
  const watch = cases.filter((c) => c.tier === "Watch");
  return (
    <div className="space-y-4">
      {urgent.length > 0 ? (
        <div>
          <QueueTable cases={urgent} />
          <QueueCards cases={urgent} />
        </div>
      ) : (
        <p className="text-sm text-muted">No Critical or Review cases right now.</p>
      )}
      {watch.length > 0 && (
        <details className="group rounded-lg border border-line bg-canvas" open={urgent.length === 0}>
          <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 text-sm text-muted [&::-webkit-details-marker]:hidden">
            <Icon name="chevron" className="h-4 w-4 transition-transform group-open:rotate-180" />
            <span className="font-semibold text-ink">Watch · {watch.length} case{watch.length === 1 ? "" : "s"}</span>
            <span className="hidden sm:inline">Low-signal cases, kept for context. Context signals alone can never raise a case above Watch.</span>
          </summary>
          <div className="border-t border-line bg-surface px-3 py-2">
            <QueueTable cases={watch} quiet />
            <QueueCards cases={watch} />
          </div>
        </details>
      )}
    </div>
  );
}

export function TierCounts({ cases }: { cases: CaseSummary[] }) {
  const n = (t: string) => cases.filter((c) => c.tier === t).length;
  return (
    <p className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted" aria-label="Cases shown by tier">
      <span><span className="font-semibold text-critical">{n("Critical")}</span> Critical</span>
      <span aria-hidden>·</span>
      <span><span className="font-semibold text-review">{n("Review")}</span> Review</span>
      <span aria-hidden>·</span>
      <span><span className="font-semibold text-ink">{n("Watch")}</span> Watch</span>
    </p>
  );
}
