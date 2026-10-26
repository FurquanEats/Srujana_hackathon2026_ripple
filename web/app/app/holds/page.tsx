import type { Metadata } from "next";
import Link from "next/link";

import { Empty, Held, Money, Notice, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { holds } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";
import { byNextDeadline, statusLabel } from "@/lib/holds";

export const metadata: Metadata = { title: "Debit holds" };

export default async function HoldsPage({ searchParams }: { searchParams: Outcome }) {
  const session = await requireRole("frm_analyst");
  const { error, done } = await searchParams;
  const list = [...(await holds(session))].sort(byNextDeadline);
  return (
    <>
      <PageHeader
        title="Temporary debit holds"
        lead="Every hold this bank placed under RBI's draft directions on money mule accounts, sorted by the next deadline. Open a hold to record the customer's explanation, the bank's decision, a police instruction or the STR."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      {list.length === 0 ? (
        <Empty>
          No holds yet. Place one from{" "}
          <Link href="/app/flags" className="underline">
            Mule flags
          </Link>
          .
        </Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[760px]">
            <thead>
              <tr>
                <th>Account</th>
                <th>Status</th>
                <th className="text-right">Held</th>
                <th>Next deadline</th>
                <th>Placed</th>
                <th aria-hidden />
              </tr>
            </thead>
            <tbody>
              {list.map((h) => {
                const next = h.deadlines.find((d) => d.due === h.next_deadline && d.state === "open");
                return (
                  <tr key={h.hold_id} className="row-link">
                    <td>
                      <Link href={`/app/holds/${h.hold_id}`} className="stretch link">
                        {h.holder_name ?? h.account_number}
                      </Link>
                      <span className="text-faint block font-mono text-xs">{h.account_number}</span>
                    </td>
                    <td className="text-[13px]">
                      {statusLabel(h)}
                      {h.mule_confirmed_at && <span className="chip ml-2">Confirmed mule</span>}
                      {h.compliance_breach && (
                        <span className="mt-1 block text-xs text-red-500">{h.compliance_breach}</span>
                      )}
                    </td>
                    <td className="text-right">
                      {h.released_at ? (
                        <Money paise={h.amount} className="text-faint" />
                      ) : (
                        <Held paise={h.amount} />
                      )}
                    </td>
                    <td className="text-[13px]">
                      {next ? (
                        <>
                          {next.name}
                          <span className="text-faint block text-xs">{formatIst(next.due)}</span>
                        </>
                      ) : (
                        <span className="text-faint">None</span>
                      )}
                    </td>
                    <td className="text-muted text-xs whitespace-nowrap">{formatIst(h.placed_at)}</td>
                    <td aria-hidden className="text-right">
                      <span className="go">→</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
