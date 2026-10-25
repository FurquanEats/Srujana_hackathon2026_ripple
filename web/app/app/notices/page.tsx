import type { Metadata } from "next";
import Link from "next/link";

import { Term } from "@/components/term";
import { Filters } from "@/components/workspace/filters";
import { Empty, Held, Money, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { notices } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Notices" };

type Search = Promise<{ status?: string; q?: string }>;

export default async function NoticesPage({ searchParams }: { searchParams: Search }) {
  const session = await requireRole("nodal_officer");
  const { status, q } = await searchParams;
  const all = [...(await notices(session))].sort((a, b) => b.received_at.localeCompare(a.received_at));
  const needle = (q ?? "").trim().toLowerCase();
  const counts = new Map<string, number>();
  for (const n of all)
    if (n.account_number) counts.set(n.account_number, (counts.get(n.account_number) ?? 0) + 1);
  const list = all.filter(
    (n) =>
      (!status ||
        (status === "held"
          ? n.held > 0
          : status === "repeat"
            ? (counts.get(n.account_number ?? "") ?? 0) > 1
            : n.status === status)) &&
      (!needle || `${n.holder_name} ${n.account_number} ${n.ack_number}`.toLowerCase().includes(needle)),
  );
  return (
    <>
      <PageHeader
        title="CFCFRMS notices"
        lead="Every notice the hub sent this bank, and Ripple's answer: how much of the victim's money reached the account, the lien on that amount only, and where the rest went next. Ripple answered each one in under a second."
      />
      <Filters
        values={{ status, q }}
        total={all.length}
        shown={list.length}
        fields={[
          {
            name: "status",
            label: "Show",
            options: [
              { value: "held", label: "With a lien" },
              { value: "repeat", label: "Accounts on more than one notice" },
              { value: "not_found", label: "No matching credit" },
            ],
          },
          { name: "q", label: "Holder, account or complaint", placeholder: "Search" },
        ]}
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
                <th>
                  <Term name="layer" />
                </th>
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
                    {(counts.get(n.account_number ?? "") ?? 0) > 1 && (
                      <span className="chip ml-2 border-red-500 text-red-600">Reported again</span>
                    )}
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
