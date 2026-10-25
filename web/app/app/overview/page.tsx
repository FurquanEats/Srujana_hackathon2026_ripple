import type { Metadata } from "next";
import Link from "next/link";

import { CardLink, Metric, Section } from "@/components/workspace/cards";
import { Held, Money, PageHeader, Priority } from "@/components/workspace/ui";
import { formatInr, formatIst } from "@/lib/format";
import { statusLabel } from "@/lib/holds";
import { cases, holdReports, holds, liens, muleCases, notices, now } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";
import { institutionName } from "@/lib/personas";
import type { DemoSession } from "@/lib/session";

export const metadata: Metadata = { title: "Overview" };

const DAY = 86_400_000;

function dueIn(due: string, clock: string): string {
  const days = Math.round((new Date(due).getTime() - new Date(clock).getTime()) / DAY);
  if (days < 0) return `${-days} days overdue`;
  if (days === 0) return "due today";
  return `in ${days} day${days === 1 ? "" : "s"}`;
}

async function Nodal({ session }: { session: DemoSession }) {
  const [list, held] = await Promise.all([notices(session), liens(session)]);
  const matched = list.filter((n) => n.status === "matched");
  const active = held.filter((l) => !l.released_at);
  const tracedIn = matched.reduce((s, n) => s + n.traced_in, 0);
  const latest = [...list].sort((a, b) => b.received_at.localeCompare(a.received_at)).slice(0, 5);
  return (
    <>
      <div className="mb-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Notices answered"
          value={list.length}
          href="/app/notices"
          note="Every one answered automatically"
        />
        <Metric label="Victim money traced in" value={<Money paise={tracedIn} />} href="/app/notices" />
        <Metric label="Active liens" value={active.length} href="/app/liens" />
        <Metric
          label="Held on liens"
          value={<Held paise={active.reduce((s, l) => s + l.amount, 0)} />}
          href="/app/liens"
        />
      </div>
      <Section
        title="Latest notices"
        action={
          <Link href="/app/notices" className="link text-[13px]">
            All notices
          </Link>
        }
      >
        <div className="grid gap-2">
          {latest.map((n) => (
            <CardLink
              key={n.notice_id}
              href={`/app/notices/${n.notice_id}`}
              title={`${n.holder_name ?? "Account not found"}, layer ${n.layer}`}
            >
              {formatIst(n.received_at)} · complaint {n.ack_number} · {formatInr(n.traced_in)} traced in
              {n.held > 0 ? `, ${formatInr(n.held)} liened` : ", nothing left to hold"}
            </CardLink>
          ))}
        </div>
      </Section>
      <Section title="Before money leaves">
        <CardLink href="/app/payment-check" title="Check a payment">
          Ask DPIP about the payee and weigh the customer&apos;s own history before a large or unusual payment
          goes.
        </CardLink>
      </Section>
    </>
  );
}

async function Frm({ session }: { session: DemoSession }) {
  const [flagged, queue, clock] = await Promise.all([muleCases(session), holds(session), now(session)]);
  const open = flagged.filter((c) => c.flags.some((f) => f.status === "open"));
  const active = queue.filter((h) => !h.released_at);
  const due = active.flatMap((h) => h.deadlines.filter((d) => d.state === "open").map((d) => ({ h, d })));
  due.sort((a, b) => a.d.due.localeCompare(b.d.due));
  const strDue = active.filter((h) => h.mule_confirmed_at && !h.str_filed_at);
  const breaches = queue.filter((h) => h.compliance_breach);
  const top = [...open]
    .sort((a, b) => ({ high: 0, medium: 1, low: 2 })[a.priority] - { high: 0, medium: 1, low: 2 }[b.priority])
    .slice(0, 5);
  return (
    <>
      <div className="mb-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Open flags, high priority"
          value={open.filter((c) => c.priority === "high").length}
          href="/app/flags"
          note={`${open.length} accounts flagged in all`}
        />
        <Metric
          label="Active debit holds"
          value={active.length}
          href="/app/holds"
          note={`${formatInr(active.reduce((s, h) => s + h.amount, 0))} on hold`}
        />
        <Metric
          label="STRs to file"
          value={strDue.length}
          href="/app/holds"
          note="7 working days from confirming a mule"
        />
        <Metric
          label="Compliance breaches"
          value={breaches.length}
          href="/app/holds"
          note={breaches.length ? "Act on these first" : "None"}
        />
      </div>
      <Section
        title="Next deadlines"
        action={
          <Link href="/app/holds" className="link text-[13px]">
            All holds
          </Link>
        }
      >
        {due.length === 0 ? (
          <p className="text-muted text-sm">No open deadlines.</p>
        ) : (
          <div className="grid gap-2">
            {due.slice(0, 6).map(({ h, d }) => (
              <CardLink
                key={`${h.hold_id}-${d.name}`}
                href={`/app/holds/${h.hold_id}`}
                title={`${d.name}: ${h.holder_name ?? h.account_number}`}
              >
                {dueIn(d.due, clock)} ({formatIst(d.due)}) · {statusLabel(h)} · {d.rule}
              </CardLink>
            ))}
          </div>
        )}
      </Section>
      <Section
        title="Highest priority flags"
        action={
          <Link href="/app/flags" className="link text-[13px]">
            All flags
          </Link>
        }
      >
        <div className="grid gap-2">
          {top.map((c) => (
            <Link key={c.account_number} href={`/app/flags/${c.account_number}`} className="card-link">
              <span className="flex flex-wrap items-center gap-2">
                <Priority level={c.priority} />
                <span className="text-fg text-sm">{c.holder_name}</span>
                <span className="text-faint font-mono text-xs">{c.account_number}</span>
                <span aria-hidden className="go ml-auto">
                  →
                </span>
              </span>
              <span className="text-muted mt-1 block text-[13px]">{c.flags[0]?.reason}</span>
            </Link>
          ))}
        </div>
      </Section>
    </>
  );
}

async function Police({ session }: { session: DemoSession }) {
  const [list, reports] = await Promise.all([cases(session), holdReports(session)]);
  const waiting = reports.filter((r) => !r.instruction && !r.released_at);
  const sum = (k: "reported" | "held" | "cashed_out") => list.reduce((s, c) => s + c[k], 0);
  return (
    <>
      <div className="mb-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Complaints" value={list.length} href="/app/cases" />
        <Metric label="Reported by victims" value={<Money paise={sum("reported")} />} href="/app/cases" />
        <Metric label="Held across banks" value={<Held paise={sum("held")} />} href="/app/cases" />
        <Metric
          label="Hold reports waiting for you"
          value={waiting.length}
          href="/app/hold-reports"
          note="Banks release on day 31 without an instruction"
        />
      </div>
      <Section
        title="Latest complaints"
        action={
          <Link href="/app/cases" className="link text-[13px]">
            All cases
          </Link>
        }
      >
        <div className="grid gap-2">
          {[...list]
            .sort((a, b) => b.filed_at.localeCompare(a.filed_at))
            .slice(0, 6)
            .map((c) => (
              <CardLink
                key={c.ack_number}
                href={`/app/cases/${c.ack_number}`}
                title={`${c.victim_name}, complaint ${c.ack_number}`}
              >
                Reported {formatInr(c.reported)} · held {formatInr(c.held)} · cashed out{" "}
                {formatInr(c.cashed_out)}
              </CardLink>
            ))}
        </div>
      </Section>
      {waiting.length > 0 && (
        <Section title="Holds reported to you">
          <div className="grid gap-2">
            {waiting.map((r) => (
              <CardLink
                key={r.hold_id}
                href="/app/hold-reports"
                title={`${r.holder_name}, ${institutionName(r.member, true)}`}
              >
                {formatInr(r.amount)} on hold · reported {formatIst(r.reported_at ?? r.placed_at)}
              </CardLink>
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

export default async function OverviewPage() {
  const session = await requireRole("nodal_officer", "frm_analyst", "police_officer");
  const lead =
    session.role === "police_officer"
      ? "Every complaint's money across the network, and the temporary debit holds banks have reported to you."
      : session.role === "frm_analyst"
        ? "Mule flags, holds and their legal deadlines at this bank, nearest first."
        : "CFCFRMS notices this bank answered and the liens that hold victims' money.";
  return (
    <>
      <PageHeader title="Overview" lead={lead} />
      {session.role === "nodal_officer" && <Nodal session={session} />}
      {session.role === "frm_analyst" && <Frm session={session} />}
      {session.role === "police_officer" && <Police session={session} />}
    </>
  );
}
