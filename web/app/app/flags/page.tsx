import type { Metadata } from "next";
import Link from "next/link";

import { Term } from "@/components/term";
import { Filters } from "@/components/workspace/filters";
import { Empty, Money, Notice, PageHeader, Priority } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { muleCases } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Mule flags" };

const ORDER = { high: 0, medium: 1, low: 2 } as const;

type Search = Promise<{ error?: string; done?: string; priority?: string; rule?: string; q?: string }>;

export default async function FlagsPage({ searchParams }: { searchParams: Search }) {
  const session = await requireRole("frm_analyst");
  const { error, done, priority, rule, q } = await searchParams;
  const all = (await muleCases(session)).filter(
    (c) => c.flags.some((f) => f.status === "open") || c.active_hold_id,
  );
  const needle = (q ?? "").trim().toLowerCase();
  const list = all.filter(
    (c) =>
      (!priority || c.priority === priority) &&
      (!rule || c.rules.includes(rule)) &&
      (!needle || `${c.holder_name} ${c.account_number}`.toLowerCase().includes(needle)),
  );
  const rules = [...new Map(all.flatMap((c) => c.flags.map((f) => [f.rule, f.title] as const))).entries()];
  list.sort((a, b) => ORDER[a.priority] - ORDER[b.priority] || b.last_at.localeCompare(a.last_at));
  return (
    <>
      <PageHeader
        title="Mule flags"
        lead="Accounts at this bank that a detection rule flagged, highest priority first. Each flag cites the transactions behind it. Open one to place a temporary debit hold or dismiss it with a reason."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      <Filters
        values={{ priority, rule, q }}
        total={all.length}
        shown={list.length}
        fields={[
          {
            name: "priority",
            label: "Priority",
            options: [
              { value: "high", label: "High" },
              { value: "medium", label: "Medium" },
              { value: "low", label: "Low" },
            ],
          },
          { name: "rule", label: "Rule", options: rules.map(([value, label]) => ({ value, label })) },
          { name: "q", label: "Holder or account", placeholder: "Search" },
        ]}
      />
      <p className="text-muted mb-3 text-sm">
        <strong className="font-medium">Priority</strong> is high when the account is linked to a CFCFRMS
        notice or three or more rules fired, medium for two rules, and low for one.
      </p>
      {list.length === 0 ? (
        <Empty>No open flags. Every flag has been held or dismissed.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[720px]">
            <thead>
              <tr>
                <th>
                  <Term name="priority" below />
                </th>
                <th>Account</th>
                <th>Why it was flagged</th>
                <th className="text-right">Flagged amount</th>
                <th>Last activity</th>
                <th aria-hidden />
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.account_number} className="row-link">
                  <td>
                    <Priority level={c.priority} />
                  </td>
                  <td>
                    <Link href={`/app/flags/${c.account_number}`} className="stretch link">
                      {c.holder_name ?? "Unnamed holder"}
                    </Link>
                    <span className="text-faint block font-mono text-xs">{c.account_number}</span>
                  </td>
                  <td className="max-w-md">
                    <span className="flex flex-wrap gap-1">
                      {[...new Set(c.flags.map((f) => f.title))].map((t) => (
                        <span key={t} className="chip">
                          {t}
                        </span>
                      ))}
                      {c.reported && <span className="chip">On a CFCFRMS notice</span>}
                      {c.active_hold_id && <span className="chip border-accent">Hold active</span>}
                    </span>
                    <span className="text-muted mt-1.5 block text-xs leading-snug">{c.flags[0]?.reason}</span>
                  </td>
                  <td className="text-right">
                    <Money paise={c.flagged_amount} />
                  </td>
                  <td className="text-muted whitespace-nowrap text-xs">{formatIst(c.last_at)}</td>
                  <td aria-hidden className="text-right">
                    <span className="go">→</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
