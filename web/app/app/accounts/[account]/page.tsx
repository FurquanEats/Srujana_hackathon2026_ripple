import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Attention, Explainer, type QuickAction, type Tone } from "@/components/workspace/attention";
import { FlowGraph } from "@/components/workspace/flow-graph";
import { PrintButton } from "@/components/workspace/print-button";
import { Held, Money, PageHeader, Priority } from "@/components/workspace/ui";
import { accountText, EXIT, RAIL } from "@/lib/accounts";
import { formatInr, formatIst } from "@/lib/format";
import { accountFlow } from "@/lib/flows";
import { account, GatewayFailure, now } from "@/lib/gateway/source";
import type { AccountView } from "@/lib/gateway/types";
import { requireRole } from "@/lib/guard";
import { statusLabel } from "@/lib/holds";

export const metadata: Metadata = { title: "Account" };

export default async function AccountPage({ params }: { params: Promise<{ account: string }> }) {
  const session = await requireRole("nodal_officer", "frm_analyst");
  const { account: number } = await params;
  if (!/^[0-9A-Z]{6,20}$/.test(number)) notFound();
  let a: AccountView;
  try {
    a = await account(session, number);
  } catch (error) {
    if (error instanceof GatewayFailure && error.status === 404) notFound();
    throw error;
  }
  const clock = await now(session);
  const flow = accountFlow(a, clock);
  const openFlags = a.flags.flatMap((c) => c.flags.filter((f) => f.status === "open"));
  const activeHold = a.holds.find((h) => !h.released_at);
  const activeLiens = a.liens.filter((l) => !l.released_at);
  const frm = session.role === "frm_analyst";

  let tone: Tone = "done";
  let title = "No action needed on this account";
  const actions: QuickAction[] = [];
  let why = "There are no open flags, active holds or liens.";
  if (a.notices.length >= 2) {
    tone = "urgent";
    title = `Reported ${a.notices.length} times on CFCFRMS`;
    why =
      "An account reported more than once may need its digital banking suspended. Only the police can direct that, under BNSS section 106; Ripple suggests it and never applies it (PRD N8).";
  } else if (frm && openFlags.length && !activeHold) {
    tone = "action";
    title = `${openFlags.length} open mule flag${openFlags.length === 1 ? "" : "s"} to review`;
    why = "Place a temporary debit hold on the flagged amount, or dismiss the flags with a reason.";
    actions.push({ label: "Review the flags", href: `/app/flags/${a.account_number}`, primary: true });
  } else if (activeHold) {
    tone = "action";
    title = `Temporary debit hold: ${statusLabel(activeHold).toLowerCase()}`;
    why = `${formatInr(activeHold.amount)} is on hold. Next deadline: ${activeHold.next_deadline ? formatIst(activeHold.next_deadline) : "none"}.`;
    if (frm)
      actions.push({ label: "Open the hold", href: `/app/holds/${activeHold.hold_id}`, primary: true });
  } else if (activeLiens.length) {
    tone = "info";
    title = `${activeLiens.length} lien${activeLiens.length === 1 ? "" : "s"} in force`;
    why = "Liens hold victims' money until the police or a court orders a release.";
  }
  if (!frm && activeLiens.length) actions.push({ label: "Manage liens", href: "/app/liens" });
  if (a.notices[0])
    actions.push({ label: "Open the latest notice", href: `/app/notices/${a.notices[0].notice_id}` });

  return (
    <>
      <PageHeader
        title={a.holder_name}
        back={{ href: frm ? "/app/flags" : "/app/notices", label: frm ? "Mule flags" : "Notices" }}
        lead={`Account ${a.account_number} · ${a.ifsc}${a.vpa ? ` · ${a.vpa}` : ""}`}
      />
      <Attention
        tone={tone}
        title={title}
        actions={actions}
        facts={[
          { label: "Balance", value: <Money paise={a.balance} /> },
          { label: "Under lien", value: a.liened ? <Held paise={a.liened} /> : "₹0" },
          { label: "On temporary hold", value: a.on_hold ? <Held paise={a.on_hold} /> : "₹0" },
          { label: "Free to use", value: <Money paise={a.available} /> },
        ]}
      >
        {why}
      </Attention>

      <FlowGraph
        title={flow.windowed ? "Money in and out, last 30 days" : "Money in and out, latest transactions"}
        centre={{ label: a.holder_name, sub: a.account_number }}
        inflows={flow.inflows}
        outflows={flow.outflows}
        events={flow.events}
        caption={`${formatInr(a.credits_30d)} in and ${formatInr(a.debits_30d)} out in the last 30 days, with ${a.counterparties_30d} different counterparties.`}
      />

      <section className="mb-10 grid gap-6 lg:grid-cols-2">
        <div className="border-line border p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="pixel text-lg">KYC and linked accounts</h2>
            <PrintButton label="Print KYC pack" />
          </div>
          <dl className="grid grid-cols-[150px_minmax(0,1fr)] gap-y-2 text-sm">
            <dt className="text-faint">Holder</dt>
            <dd>{a.holder_name}</dd>
            <dt className="text-faint">Declared profile</dt>
            <dd>{a.declared_profile}</dd>
            <dt className="text-faint">Account type</dt>
            <dd>{a.account_type}</dd>
            <dt className="text-faint">Opened</dt>
            <dd>{formatIst(a.opened_at)}</dd>
            <dt className="text-faint">IFSC</dt>
            <dd className="font-mono">{a.ifsc}</dd>
            <dt className="text-faint">Linked UPI ID</dt>
            <dd className="font-mono">{a.vpa ?? "None"}</dd>
          </dl>
          <p className="text-faint mt-3 text-xs">
            The SOP asks the bank to upload KYC and linked accounts within a week of a notice; Ripple has it
            ready at once (PRD N7).
          </p>
        </div>
        <div className="border-line border p-5">
          <h2 className="pixel mb-3 text-lg">On record</h2>
          <ul className="grid gap-2 text-sm">
            {a.notices.map((n) => (
              <li key={n.notice_id}>
                <Link className="link" href={`/app/notices/${n.notice_id}`}>
                  CFCFRMS notice, complaint {n.ack_number}
                </Link>{" "}
                <span className="text-faint">
                  · layer {n.layer} · {formatInr(n.traced_in)} traced in
                </span>
              </li>
            ))}
            {a.liens.map((l) => (
              <li key={l.lien_id}>
                Lien {formatInr(l.amount)} for {l.ack_number}{" "}
                <span className="text-faint">
                  · {l.released_at ? `released ${formatIst(l.released_at)}` : "in force"}
                </span>
              </li>
            ))}
            {a.flags.map((c) => (
              <li key={c.account_number} className="flex flex-wrap items-center gap-2">
                <Priority level={c.priority} />
                {frm ? (
                  <Link className="link" href={`/app/flags/${c.account_number}`}>
                    {c.flags.length} mule flag{c.flags.length === 1 ? "" : "s"}
                  </Link>
                ) : (
                  <span>{c.flags.length} mule flags</span>
                )}
              </li>
            ))}
            {a.holds.map((h) => (
              <li key={h.hold_id}>
                {frm ? (
                  <Link className="link" href={`/app/holds/${h.hold_id}`}>
                    Temporary debit hold {formatInr(h.amount)}
                  </Link>
                ) : (
                  `Temporary debit hold ${formatInr(h.amount)}`
                )}{" "}
                <span className="text-faint">· {statusLabel(h)}</span>
              </li>
            ))}
            {!a.notices.length && !a.liens.length && !a.flags.length && !a.holds.length && (
              <li className="text-faint">Nothing on record.</li>
            )}
          </ul>
        </div>
      </section>

      <section>
        <h2 className="pixel mb-3 text-lg">Statement</h2>
        <div className="overflow-x-auto">
          <table className="table min-w-[720px]">
            <thead>
              <tr>
                <th>When</th>
                <th>Transaction</th>
                <th>Counterparty</th>
                <th className="text-right">In</th>
                <th className="text-right">Out</th>
              </tr>
            </thead>
            <tbody>
              {a.statement.map((l) => (
                <tr key={l.txn_id}>
                  <td className="text-muted text-xs whitespace-nowrap">{formatIst(l.at)}</td>
                  <td className="text-xs">
                    {l.exit ? EXIT[l.exit.mode] : RAIL[l.rail]}
                    <span className="text-faint block font-mono">{l.reference}</span>
                  </td>
                  <td className="text-xs">
                    {l.exit
                      ? `${l.exit.identifier}${l.exit.location ? `, ${l.exit.location}` : ""}`
                      : accountText(l.counterparty)}
                  </td>
                  <td className="text-right">{l.direction === "credit" ? <Money paise={l.amount} /> : ""}</td>
                  <td className={`text-right ${l.exit ? "text-red-600" : ""}`}>
                    {l.direction === "debit" ? <Money paise={l.amount} /> : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <Explainer title="Where this comes from">
        <p>
          Everything here is the bank&apos;s own record of its own customer: Ripple never sees another
          bank&apos;s accounts.
        </p>
        <p>
          &quot;Free to use&quot; is the balance less liens and temporary holds. The ledger refuses any debit
          that would touch held money.
        </p>
      </Explainer>
    </>
  );
}
