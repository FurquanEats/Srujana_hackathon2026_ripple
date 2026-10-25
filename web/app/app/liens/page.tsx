import type { Metadata } from "next";

import { Empty, Held, Money, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { liens } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Liens" };

export default async function LiensPage() {
  const session = await requireRole("nodal_officer");
  const list = [...(await liens(session))].sort((a, b) => b.placed_at.localeCompare(a.placed_at));
  const active = list.filter((l) => !l.released_at).reduce((sum, l) => sum + l.amount, 0);
  return (
    <>
      <PageHeader
        title="Liens"
        lead={
          <>
            Liens Ripple placed on traced amounts when answering notices. Active liens hold{" "}
            <Money paise={active} /> of victims&apos; money at this institution. Each lien covers the
            victim&apos;s money only, never the whole account.
          </>
        }
      />
      {list.length === 0 ? (
        <Empty>No liens at this institution: no victim money is still here.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[700px]">
            <thead>
              <tr>
                <th>Account</th>
                <th>Acknowledgement</th>
                <th className="text-right">Amount</th>
                <th>Basis</th>
                <th>Placed</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {list.map((l) => (
                <tr key={l.lien_id}>
                  <td>
                    {l.holder_name ?? "Unnamed holder"}
                    <span className="text-faint block font-mono text-xs">{l.account_number}</span>
                  </td>
                  <td className="font-mono text-xs">{l.ack_number}</td>
                  <td className="text-right">
                    {l.released_at ? (
                      <Money paise={l.amount} className="text-faint" />
                    ) : (
                      <Held paise={l.amount} />
                    )}
                  </td>
                  <td className="text-muted text-xs">{l.basis}</td>
                  <td className="text-muted text-xs whitespace-nowrap">{formatIst(l.placed_at)}</td>
                  <td className="text-xs">
                    {l.released_at ? `Released ${formatIst(l.released_at)}` : "Active"}
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
