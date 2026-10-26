import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Attention, Explainer } from "@/components/workspace/attention";
import { FlowGraph } from "@/components/workspace/flow-graph";
import { Money, Notice, PageHeader, Priority } from "@/components/workspace/ui";
import { creditsFlow } from "@/lib/flows";
import { formatInr, formatIst } from "@/lib/format";
import { account as accountView, muleCases, now } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";
import { institutionName } from "@/lib/personas";

import { dismissFlags, placeHold } from "../../actions";
import { HoldForm } from "./hold-form";

export const metadata: Metadata = { title: "Flagged account" };

export default async function FlagPage({
  params,
  searchParams,
}: {
  params: Promise<{ account: string }>;
  searchParams: Outcome;
}) {
  const session = await requireRole("frm_analyst");
  const { account } = await params;
  const { error, done } = await searchParams;
  const found = (await muleCases(session, true)).find((c) => c.account_number === account);
  if (!found) notFound();
  const open = found.flags.filter((f) => f.status === "open");
  const profile = await accountView(session, found.account_number).catch(() => null);
  // The node holds only money still in the account, so with nothing free there is nothing to hold.
  const holdable = profile ? Math.min(profile.available, Math.max(0, ...open.map((f) => f.amount))) : null;
  const flow = profile ? creditsFlow(profile, [...new Set(found.flags.flatMap((f) => f.credit_txns))]) : null;
  return (
    <>
      <PageHeader
        title={found.holder_name ?? found.account_number}
        back={{ href: "/app/flags", label: "Mule flags" }}
        lead={
          <>
            Account <span className="font-mono">{found.account_number}</span>. {found.declared_profile}.
          </>
        }
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      {found.active_hold_id ? (
        <Attention
          tone="info"
          title="A temporary debit hold is in force on this account"
          actions={[
            { label: "Open the hold", href: `/app/holds/${found.active_hold_id}`, primary: true },
            { label: "Open the account", href: `/app/accounts/${found.account_number}` },
          ]}
        >
          Work the hold&apos;s deadlines from its page. New flags on this account will appear here.
        </Attention>
      ) : open.length > 0 && holdable === 0 ? (
        <Attention
          tone="info"
          title="The flagged money has already left this account"
          actions={[
            { label: "Dismiss with a reason", href: "#dismiss", primary: true },
            { label: "Open the account", href: `/app/accounts/${found.account_number}` },
          ]}
          facts={[
            { label: "Priority", value: <Priority level={found.priority} /> },
            { label: "Flagged amount", value: <Money paise={found.flagged_amount} /> },
            { label: "Free balance now", value: <Money paise={0} /> },
            { label: "Last activity", value: formatIst(found.last_at) },
          ]}
        >
          A temporary debit hold can only stop money that is still here. Follow where it went on the graph
          below; if the account is part of a scam, report it through NCRP so CFCFRMS can trace it onward.
          Dismiss the flags if the activity is ordinary.
        </Attention>
      ) : open.length > 0 ? (
        <Attention
          tone={found.priority === "high" ? "urgent" : "action"}
          title={`Decide: hold ${formatInr(holdable ?? Math.max(...open.map((f) => f.amount)))} or dismiss`}
          actions={[
            { label: "Place a temporary debit hold", href: "#hold", primary: true },
            { label: "Dismiss with a reason", href: "#dismiss" },
            { label: "Open the account", href: `/app/accounts/${found.account_number}` },
          ]}
          facts={[
            { label: "Priority", value: <Priority level={found.priority} /> },
            { label: "Open flags", value: open.length },
            { label: "Flagged amount", value: <Money paise={found.flagged_amount} /> },
            { label: "Last activity", value: formatIst(found.last_at) },
          ]}
        >
          {found.priority_reason} Money that has already left cannot be held, so act while it is still in the
          account.
        </Attention>
      ) : (
        <Attention
          tone="done"
          title="Every flag on this account is closed"
          actions={[{ label: "Open the account", href: `/app/accounts/${found.account_number}` }]}
        />
      )}
      {flow && flow.inflows.length > 0 && (
        <FlowGraph
          title="The flagged credits, and what left in the next two days"
          centre={{ label: found.holder_name ?? found.account_number, sub: found.account_number }}
          inflows={flow.inflows}
          outflows={flow.outflows}
          events={flow.events}
        />
      )}

      <section aria-labelledby="flags" className="mb-10">
        <h2 id="flags" className="pixel mb-4 text-lg">
          Flags
        </h2>
        <ul className="grid gap-3">
          {found.flags.map((f) => (
            <li key={f.key} className="border-line border p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="text-fg text-sm font-normal">{f.title}</p>
                <span className="text-faint text-xs">
                  {f.status === "open" ? "Open" : f.status === "held" ? "Held" : "Dismissed"} ·{" "}
                  {formatIst(f.at)}
                </span>
              </div>
              <p className="text-muted mt-2 text-sm leading-relaxed">{f.reason}</p>
              <p className="text-faint mt-2 text-xs">
                Cites <span className="font-mono">{f.cited_txns.join(", ")}</span> ·{" "}
                <Money paise={f.amount} />
              </p>
              {f.dismissed_reason && (
                <p className="text-muted mt-2 text-xs">Dismissed: {f.dismissed_reason}</p>
              )}
            </li>
          ))}
        </ul>
      </section>

      {found.active_hold_id ? (
        <p className="text-sm">
          This account has an active temporary debit hold.{" "}
          <Link href={`/app/holds/${found.active_hold_id}`} className="underline underline-offset-2">
            Open the hold
          </Link>
          .
        </p>
      ) : open.length > 0 ? (
        <div className="grid gap-8 lg:grid-cols-[1fr_1fr]">
          {holdable === 0 ? (
            <section className="border-line border p-5 text-sm">
              <h2 className="pixel mb-1 text-lg">Nothing left to hold</h2>
              <p className="text-muted">
                The account&apos;s free balance is ₹0, so a hold would stop nothing.
              </p>
            </section>
          ) : (
            <section id="hold" aria-labelledby="hold-title" className="border-line scroll-mt-6 border p-5">
              <h2 id="hold-title" className="pixel mb-1 text-lg">
                Place a temporary debit hold
              </h2>
              <p className="text-muted mb-5 text-[13px]">
                The hold covers the flagged amount only, unless you give a written reason for the whole
                account. The customer is told at once and has 20 days to explain (RBI draft directions, Annex
                III).
              </p>
              <HoldForm
                action={placeHold}
                account={found.account_number}
                holder={found.holder_name ?? "customer"}
                bank={institutionName(session.member)}
                today={await now(session)}
                flags={open.map((f) => ({
                  key: f.key,
                  title: f.title,
                  reason: f.reason,
                  amount: f.amount,
                  label: formatInr(f.amount),
                }))}
              />
            </section>
          )}
          <section
            id="dismiss"
            aria-labelledby="dismiss-title"
            className="border-line scroll-mt-6 border p-5"
          >
            <h2 id="dismiss-title" className="pixel mb-1 text-lg">
              Dismiss the flags
            </h2>
            <p className="text-muted mb-5 text-[13px]">
              If the activity has an ordinary explanation, dismiss the open flags. Your reason is kept in the
              audit log and counts against the rule in the next shadow run.
            </p>
            <form action={dismissFlags} className="grid gap-4">
              <input type="hidden" name="account" value={found.account_number} />
              <div>
                <label htmlFor="reason" className="label">
                  Reason
                </label>
                <textarea
                  id="reason"
                  name="reason"
                  required
                  minLength={10}
                  maxLength={2000}
                  rows={4}
                  className="field"
                />
              </div>
              <button className="button button-ghost justify-self-start">Dismiss open flags</button>
            </form>
          </section>
        </div>
      ) : (
        <p className="text-muted text-sm">Every flag on this account is closed.</p>
      )}
      <Explainer title="The rules behind these flags">
        <p>
          Only credits of ₹1,000 or more are flagged (RBI draft, Annex III 3(8)). Each flag cites the
          transactions behind it.
        </p>
        <p>
          Priority is high when the account is linked to a CFCFRMS notice or three or more rules fire, medium
          for two, low for one. The thresholds are this bank&apos;s own, set on the Detection page.
        </p>
        <p>
          A hold covers the flagged amount only. Holding the whole account needs a written reason of at least
          30 characters (Annex III para 6(ii)).
        </p>
      </Explainer>
    </>
  );
}
