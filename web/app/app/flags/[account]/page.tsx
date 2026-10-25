import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Money, Notice, PageHeader, Priority } from "@/components/workspace/ui";
import { formatInr, formatIst } from "@/lib/format";
import { muleCases, now } from "@/lib/gateway/source";
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
      <div className="mb-8 flex flex-wrap items-center gap-2 text-sm">
        <Priority level={found.priority} />
        <span className="text-muted">{found.priority_reason}</span>
      </div>

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
          <section aria-labelledby="hold" className="border-line border p-5">
            <h2 id="hold" className="pixel mb-1 text-lg">
              Place a temporary debit hold
            </h2>
            <p className="text-muted mb-5 text-[13px]">
              The hold covers the flagged amount only, unless you give a written reason for the whole account.
              The customer is told at once and has 20 days to explain (RBI draft directions, Annex III).
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
          <section aria-labelledby="dismiss" className="border-line border p-5">
            <h2 id="dismiss" className="pixel mb-1 text-lg">
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
    </>
  );
}
