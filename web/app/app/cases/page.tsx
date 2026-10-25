import type { Metadata } from "next";
import Link from "next/link";

import { Empty, Held, Money, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { cases } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Cases" };

export default async function CasesPage() {
  const session = await requireRole("police_officer", "demo");
  const list = [...(await cases(session))].sort((a, b) => b.filed_at.localeCompare(a.filed_at));
  return (
    <>
      <PageHeader
        title="Cases"
        lead="Every complaint filed on CFCFRMS and what happened to the money: held by a lien, cashed out, gone off the network, or still being traced. The four always add up to the amount reported."
      />
      {list.length === 0 ? (
        <Empty>No complaints yet.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[760px]">
            <thead>
              <tr>
                <th>Acknowledgement</th>
                <th>Victim</th>
                <th className="text-right">Reported</th>
                <th className="text-right">Held</th>
                <th className="text-right">Cashed out</th>
                <th>Trail</th>
                <th>Filed</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.ack_number}>
                  <td>
                    <Link
                      href={`/app/cases/${c.ack_number}`}
                      className="text-fg font-mono underline-offset-2 hover:underline"
                    >
                      {c.ack_number}
                    </Link>
                  </td>
                  <td>{c.victim_name}</td>
                  <td className="text-right">
                    <Money paise={c.reported} />
                  </td>
                  <td className="text-right">
                    {c.held > 0 ? <Held paise={c.held} /> : <span className="text-faint">₹0</span>}
                  </td>
                  <td className="text-right">
                    <Money paise={c.cashed_out} />
                  </td>
                  <td className="text-xs">
                    {c.complete ? "Complete" : <span className="text-muted">Tracing</span>}
                  </td>
                  <td className="text-muted text-xs whitespace-nowrap">{formatIst(c.filed_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
