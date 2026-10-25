import type { Metadata } from "next";
import Link from "next/link";

import { Empty, Money, Notice, PageHeader, Priority } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { muleCases } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";

export const metadata: Metadata = { title: "Mule flags" };

const ORDER = { high: 0, medium: 1, low: 2 } as const;

export default async function FlagsPage({ searchParams }: { searchParams: Outcome }) {
  const session = await requireRole("frm_analyst");
  const { error, done } = await searchParams;
  const list = (await muleCases(session)).filter(
    (c) => c.flags.some((f) => f.status === "open") || c.active_hold_id,
  );
  list.sort((a, b) => ORDER[a.priority] - ORDER[b.priority] || b.last_at.localeCompare(a.last_at));
  return (
    <>
      <PageHeader
        title="Mule flags"
        lead="Accounts at this bank that a detection rule flagged, highest priority first. Each flag cites the transactions behind it. Open one to place a temporary debit hold or dismiss it with a reason."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      {list.length === 0 ? (
        <Empty>No open flags. Every flag has been held or dismissed.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[720px]">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Account</th>
                <th>Why it was flagged</th>
                <th className="text-right">Flagged amount</th>
                <th>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.account_number}>
                  <td>
                    <Priority level={c.priority} />
                  </td>
                  <td>
                    <Link
                      href={`/app/flags/${c.account_number}`}
                      className="text-fg underline-offset-2 hover:underline"
                    >
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
