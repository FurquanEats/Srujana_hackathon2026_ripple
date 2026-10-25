import type { Metadata } from "next";
import Link from "next/link";

import { Filters } from "@/components/workspace/filters";
import { Empty, Held, Money, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { cases } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Cases" };

type Search = Promise<{ state?: string; q?: string }>;

export default async function CasesPage({ searchParams }: { searchParams: Search }) {
  const session = await requireRole("police_officer", "demo");
  const { state, q } = await searchParams;
  const all = [...(await cases(session))].sort((a, b) => b.filed_at.localeCompare(a.filed_at));
  const needle = (q ?? "").trim().toLowerCase();
  const list = all.filter(
    (c) =>
      (!state || (state === "held" ? c.held > 0 : state === "tracing" ? !c.complete : c.complete)) &&
      (!needle || `${c.victim_name} ${c.ack_number}`.toLowerCase().includes(needle)),
  );
  return (
    <>
      <PageHeader
        title="Cases"
        lead="Every complaint filed on CFCFRMS and what happened to the money: held by a lien, cashed out, gone off the network, or still being traced. The four always add up to the amount reported."
      />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        {session.role === "police_officer" && (
          <Link href="/app/cases/new" className="button button-solid">
            File a complaint
          </Link>
        )}
      </div>
      <Filters
        values={{ state, q }}
        total={all.length}
        shown={list.length}
        fields={[
          {
            name: "state",
            label: "Show",
            options: [
              { value: "held", label: "Money held" },
              { value: "tracing", label: "Still tracing" },
              { value: "complete", label: "Trail complete" },
            ],
          },
          { name: "q", label: "Victim or acknowledgement", placeholder: "Search" },
        ]}
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
                <th aria-hidden />
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.ack_number} className="row-link">
                  <td>
                    <Link href={`/app/cases/${c.ack_number}`} className="stretch link font-mono">
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
