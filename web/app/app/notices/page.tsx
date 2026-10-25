import type { Metadata } from "next";
import Link from "next/link";

import { Empty, Held, Money, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { notices } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Notices" };

export default async function NoticesPage() {
  const session = await requireRole("nodal_officer");
  const list = [...(await notices(session))].sort((a, b) => b.received_at.localeCompare(a.received_at));
  return (
    <>
      <PageHeader
        title="CFCFRMS notices"
        lead="Every notice the hub sent this bank, and Ripple's answer: how much of the victim's money reached the account, the lien on that amount only, and where the rest went next. Ripple answered each one in under a second."
      />
      {list.length === 0 ? (
        <Empty>No notices have reached this institution.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[760px]">
            <thead>
              <tr>
                <th>Acknowledgement</th>
                <th>Account</th>
                <th>Layer</th>
                <th className="text-right">Victim money in</th>
                <th className="text-right">Lien</th>
                <th>Onward</th>
                <th>Received</th>
                <th aria-hidden />
              </tr>
            </thead>
            <tbody>
              {list.map((n) => (
                <tr key={n.notice_id} className="row-link">
                  <td>
                    <Link href={`/app/notices/${n.notice_id}`} className="stretch link font-mono">
                      {n.ack_number}
                    </Link>
                  </td>
                  <td>
                    {n.holder_name ?? "Not found"}
                    <span className="text-faint block font-mono text-xs">{n.account_number ?? n.reason}</span>
                  </td>
                  <td>{n.layer}</td>
                  <td className="text-right">
                    <Money paise={n.traced_in} />
                  </td>
                  <td className="text-right">
                    {n.held > 0 ? <Held paise={n.held} /> : <span className="text-faint">None</span>}
                  </td>
                  <td className="text-muted text-xs">
                    {n.onward_count} hops, {n.exit_count} exits
                  </td>
                  <td className="text-muted text-xs whitespace-nowrap">{formatIst(n.received_at)}</td>
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
