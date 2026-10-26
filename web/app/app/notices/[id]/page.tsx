import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Attention, Explainer, type QuickAction } from "@/components/workspace/attention";
import { FlowGraph } from "@/components/workspace/flow-graph";
import { PrintButton } from "@/components/workspace/print-button";
import { ReleaseForm } from "@/components/workspace/release-form";
import { Held, Money, Notice as Banner, PageHeader } from "@/components/workspace/ui";
import { accountText, EXIT, RAIL } from "@/lib/accounts";
import { formatInr, formatIst } from "@/lib/format";
import { noticeFlow } from "@/lib/flows";
import { GatewayFailure, liens, notice, notices } from "@/lib/gateway/source";
import type { NoticeDetail } from "@/lib/gateway/types";
import { requireRole, type Outcome } from "@/lib/guard";

import { releaseLienAction } from "../../actions";

export const metadata: Metadata = { title: "Notice" };

const DAY = 86_400_000;

export default async function NoticePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Outcome;
}) {
  const session = await requireRole("nodal_officer");
  const { id } = await params;
  const { error, done } = await searchParams;
  if (!/^[0-9A-Za-z-]{8,64}$/.test(id)) notFound();
  let n: NoticeDetail;
  try {
    n = await notice(session, id);
  } catch (e) {
    if (e instanceof GatewayFailure && e.status === 404) notFound();
    throw e;
  }
  const s = n.summary;
  const ack = s.ack_number;
  const [all, held] = await Promise.all([notices(session), liens(session)]);
  const repeats = s.account_number ? all.filter((x) => x.account_number === s.account_number).length : 0;
  const lien = held.find((l) => l.lien_id === s.lien_id);
  const passedOn = n.onward.reduce((sum, h) => sum + h.traced_amount, 0);
  const cashedOut = n.exits.reduce((sum, e) => sum + e.traced_amount, 0);
  const kycDue = new Date(new Date(s.received_at).getTime() + 7 * DAY).toISOString();
  const flow = noticeFlow(n);

  const actions: QuickAction[] = [];
  if (s.account_number)
    actions.push({
      label: "Open KYC pack and account",
      href: `/app/accounts/${s.account_number}`,
      primary: true,
    });
  if (lien && !lien.released_at) actions.push({ label: "Record a release order", href: "#release" });
  actions.push({ label: "See the statement", href: "#statement" });

  return (
    <>
      <PageHeader
        title={s.holder_name ?? "Account not found"}
        back={{ href: "/app/notices", label: "Notices" }}
        lead={
          <>
            Notice {s.notice_id} · complaint <span className="font-mono">{ack}</span> · layer {s.layer} ·
            received {formatIst(s.received_at)}
          </>
        }
      />
      {error && <Banner kind="error">{error}</Banner>}
      {done && <Banner kind="done">{done}</Banner>}

      {s.status === "not_found" ? (
        <Attention tone="info" title="No matching credit at this bank" actions={[]}>
          Ripple answered CFCFRMS at once: {s.reason}. Nothing was held. If the complainant&apos;s details
          look wrong, the hub asks the police to correct them.
        </Attention>
      ) : repeats >= 2 ? (
        <Attention
          tone="urgent"
          title={`This account is on ${repeats} notices`}
          actions={actions}
          facts={[
            { label: "Victim money in", value: <Money paise={s.traced_in} /> },
            { label: "Liened here", value: s.held ? <Held paise={s.held} /> : "₹0" },
            { label: "Upload KYC by", value: formatIst(kycDue) },
            { label: "Answered", value: "Automatically" },
          ]}
        >
          An account reported more than once may need its digital banking suspended. Ask the investigating
          officer for a direction under BNSS section 106; Ripple suggests it and never applies it (PRD N8).
        </Attention>
      ) : (
        <Attention
          tone={lien && !lien.released_at ? "action" : "done"}
          title={
            lien && lien.released_at
              ? `Lien released ${formatIst(lien.released_at)}`
              : s.held > 0
                ? `Answered automatically. ${formatInr(s.held)} is under lien.`
                : "Answered automatically. Nothing was left to hold."
          }
          actions={actions}
          facts={[
            { label: "Victim money in", value: <Money paise={s.traced_in} /> },
            { label: "Liened here", value: s.held ? <Held paise={s.held} /> : "₹0" },
            { label: "Passed on, reported to CFCFRMS", value: <Money paise={passedOn} /> },
            { label: "Cashed out", value: <Money paise={cashedOut} /> },
          ]}
        >
          Your remaining step is the KYC and linked-account upload, due by {formatIst(kycDue)}; Ripple has it
          ready. Keep the lien until the police or a court orders a release.
        </Attention>
      )}

      {s.status === "matched" && (
        <FlowGraph
          title="Where the victim's money went from this account"
          centre={{ label: s.holder_name ?? "This account", sub: s.account_number ?? "" }}
          inflows={flow.inflows}
          outflows={flow.outflows}
          caption="Each debit takes the victim's money before the holder's own, as the MHA SOP's Annexure V examples do. Onward hops went to the next bank as CFCFRMS notices."
        />
      )}

      <section id="statement" className="mb-10 scroll-mt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="pixel text-lg">Statement around the credit</h2>
          <PrintButton label="Print the response" />
        </div>
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
                  <tr
                    key={line.txn_id}
                    className={victim > 0 ? "bg-[color-mix(in_srgb,var(--color-accent)_8%,transparent)]" : ""}
                  >
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
                      {victim > 0 ? <Held paise={victim} /> : <span className="text-faint">₹0</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {n.exits.length > 0 && (
        <section className="mb-10">
          <h2 className="pixel mb-3 text-lg">Exits reported for the police</h2>
          <ul className="grid gap-2 md:grid-cols-2">
            {n.exits.map((e) => (
              <li key={e.reference} className="border-line border p-3 text-sm">
                {EXIT[e.mode]} of {formatInr(e.traced_amount)} at{" "}
                <span className="font-mono">{e.identifier}</span>
                {e.location ? `, ${e.location}` : ""}
                <span className="text-muted block text-xs">{formatIst(e.at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {lien && !lien.released_at && (
        <section id="release" className="border-line mb-10 scroll-mt-6 border p-5">
          <h2 className="pixel mb-1 text-lg">Record a release order</h2>
          <p className="text-muted mb-4 text-sm">
            Only the police (interim custody under BNSS 106(3), SOP 11 Process 1) or a court can lift this
            lien of {formatInr(lien.amount)}. Record their order here; it goes in the audit log.
          </p>
          <ReleaseForm
            action={releaseLienAction}
            hidden={{ lien_id: lien.lien_id, back: `/app/notices/${id}` }}
            victimChoice
          />
        </section>
      )}

      <Explainer>
        <p>
          CFCFRMS sent this notice when the victim&apos;s money reached this account. Ripple matched the
          credit by its reference, amount and time (N1).
        </p>
        <p>
          It then followed every later debit in time order. A debit takes the victims&apos; money first,
          shared pro rata among victims, so the holder&apos;s own money is never liened (N2, N3). Onward
          payments carry only the victim&apos;s share to the next bank (N4), and cash-outs name the ATM,
          merchant or wallet (N5).
        </p>
        <p>
          Legal basis for the lien: {n.legal_basis}.{" "}
          <Link className="link" href="/app/liens">
            All liens
          </Link>
          .
        </p>
      </Explainer>
    </>
  );
}
