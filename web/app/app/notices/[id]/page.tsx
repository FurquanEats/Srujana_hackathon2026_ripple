import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Held, Money, PageHeader, Stat } from "@/components/workspace/ui";
import { accountText, EXIT, RAIL } from "@/lib/accounts";
import { formatIst } from "@/lib/format";
import { GatewayFailure, notice } from "@/lib/gateway/source";
import type { NoticeDetail } from "@/lib/gateway/types";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Notice" };

export default async function NoticePage({ params }: { params: Promise<{ id: string }> }) {
  const session = await requireRole("nodal_officer");
  const { id } = await params;
  if (!/^[0-9A-Za-z-]{8,64}$/.test(id)) notFound();
  let n: NoticeDetail;
  try {
    n = await notice(session, id);
  } catch (error) {
    if (error instanceof GatewayFailure && error.status === 404) notFound();
    throw error;
  }
  const s = n.summary;
  const ack = s.ack_number;
  return (
    <>
      <PageHeader
        title={s.holder_name ?? "Account not found"}
        back={{ href: "/app/notices", label: "Notices" }}
        lead={
          <>
            Notice {s.notice_id} for NCRP acknowledgement <span className="font-mono">{ack}</span>, layer{" "}
            {s.layer}. Received {formatIst(s.received_at)}.
          </>
        }
      />
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <Stat label="Victim money that reached the account">
          <Money paise={s.traced_in} />
        </Stat>
        <Stat label="Lien on the traced amount">
          {s.held > 0 ? <Held paise={s.held} /> : <span className="text-faint">None</span>}
        </Stat>
        <Stat label="Legal basis">
          <span className="text-base">{n.legal_basis}</span>
        </Stat>
      </div>
      <p className="text-muted mb-10 max-w-3xl text-sm leading-relaxed">
        Ripple applied the MHA SOP&apos;s tracing rule (Annexure V): each debit takes the victims&apos; money
        before the account holder&apos;s own, shared pro rata among victims. The lien covers only what is
        still the victim&apos;s, so the holder can keep using the rest of the account. The credit named in the
        notice was {RAIL[n.credit.rail]} {n.credit.reference} for <Money paise={n.credit.amount} /> on{" "}
        {formatIst(n.credit.at)}.
      </p>

      <section aria-labelledby="statement" className="mb-10">
        <h2 id="statement" className="pixel mb-4 text-lg">
          Statement
        </h2>
        <div className="overflow-x-auto">
          <table className="table min-w-[760px]">
            <thead>
              <tr>
                <th>Time</th>
                <th>Transaction</th>
                <th>Counterparty</th>
                <th className="text-right">Credit</th>
                <th className="text-right">Debit</th>
                <th className="text-right">Victim money</th>
              </tr>
            </thead>
            <tbody>
              {n.statement.map((line) => {
                const victim = line.victim_money[ack] ?? 0;
                return (
                  <tr key={line.txn_id}>
                    <td className="text-muted text-xs whitespace-nowrap">{formatIst(line.at)}</td>
                    <td className="text-xs">
                      {line.exit ? EXIT[line.exit.mode] : RAIL[line.rail]}
                      <span className="text-faint block font-mono">{line.reference}</span>
                    </td>
                    <td className="text-xs">
                      {line.exit
                        ? `${line.exit.identifier}${line.exit.location ? `, ${line.exit.location}` : ""}`
                        : accountText(line.counterparty)}
                    </td>
                    <td className="text-right">
                      {line.direction === "credit" ? <Money paise={line.amount} /> : ""}
                    </td>
                    <td className="text-right">
                      {line.direction === "debit" ? <Money paise={line.amount} /> : ""}
                    </td>
                    <td className="text-right">
                      {victim > 0 ? <Held paise={victim} /> : <span className="text-faint">0</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-8 lg:grid-cols-2">
        <section aria-labelledby="onward">
          <h2 id="onward" className="pixel mb-4 text-lg">
            Onward hops reported
          </h2>
          {n.onward.length === 0 ? (
            <p className="text-faint text-sm">
              None of the victim&apos;s money left this account to another account.
            </p>
          ) : (
            <ul className="grid gap-2">
              {n.onward.map((h) => (
                <li key={h.payment.reference} className="border-line border p-3 text-sm">
                  <span className="font-mono">{accountText(h.to)}</span>
                  <span className="text-muted block text-xs">
                    {RAIL[h.payment.rail]} {h.payment.reference}, {formatIst(h.payment.at)}:{" "}
                    <Money paise={h.traced_amount} /> of the victim&apos;s money in{" "}
                    <Money paise={h.payment.amount} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="exits">
          <h2 id="exits" className="pixel mb-4 text-lg">
            Exits reported
          </h2>
          {n.exits.length === 0 ? (
            <p className="text-faint text-sm">
              None of the victim&apos;s money left the banking system from this account.
            </p>
          ) : (
            <ul className="grid gap-2">
              {n.exits.map((e) => (
                <li key={e.reference} className="border-line border p-3 text-sm">
                  {EXIT[e.mode]} at <span className="font-mono">{e.identifier}</span>
                  {e.location ? `, ${e.location}` : ""}
                  <span className="text-muted block text-xs">
                    {formatIst(e.at)}: <Money paise={e.traced_amount} /> of the victim&apos;s money
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
