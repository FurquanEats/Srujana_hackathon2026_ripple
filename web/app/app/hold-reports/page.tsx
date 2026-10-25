import type { Metadata } from "next";

import { HoldTimeline } from "@/components/workspace/hold-timeline";
import { Empty, Held, Money, Notice, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { holdReports, now } from "@/lib/gateway/source";
import type { Hold } from "@/lib/gateway/types";
import { requireRole, type Outcome } from "@/lib/guard";
import { statusLabel } from "@/lib/holds";

import { policeInstructionAction } from "../actions";

export const metadata: Metadata = { title: "Hold reports" };

export default async function HoldReportsPage({ searchParams }: { searchParams: Outcome }) {
  const session = await requireRole("police_officer");
  const { error, done } = await searchParams;
  const [reports, clock] = await Promise.all([holdReports(session), now(session)]);
  reports.sort(
    (a, b) =>
      (a.instruction ? 1 : 0) - (b.instruction ? 1 : 0) ||
      (a.reported_at ?? "").localeCompare(b.reported_at ?? ""),
  );
  return (
    <>
      <PageHeader
        title="Hold reports"
        lead="Temporary debit holds that banks reported to the police through NCRP after the customer's explanation did not clear them. Without your instruction, the bank releases the hold on the 31st day from its report (RBI draft directions, Annex III Step 5)."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      {reports.length === 0 ? (
        <Empty>No bank has reported a hold to the police yet.</Empty>
      ) : (
        <div className="grid gap-6">
          {reports.map((r) => (
            <article key={r.hold_id} className="border-line border p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h2 className="text-fg text-lg">
                  {r.holder_name} <span className="text-faint font-mono text-sm">{r.account_number}</span>
                </h2>
                <span className="text-muted text-sm">
                  {r.member_name} · {statusLabel(r as unknown as Hold)}
                </span>
              </div>
              <p className="mt-2 text-sm">
                {r.released_at ? (
                  <Money paise={r.amount} className="text-faint" />
                ) : (
                  <Held paise={r.amount} />
                )}{" "}
                on hold since {formatIst(r.placed_at)}, reported {formatIst(r.reported_at ?? r.placed_at)}.
              </p>
              <ul className="text-muted mt-3 grid gap-1 text-sm">
                {r.reasons.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
              {r.decision_reason && (
                <p className="text-muted mt-3 text-sm">The bank&apos;s grounds: {r.decision_reason}</p>
              )}
              <HoldTimeline hold={r as unknown as Hold} now={clock} />
              {!r.instruction && !r.released_at ? (
                <form
                  action={policeInstructionAction}
                  className="mt-6 grid gap-3 sm:grid-cols-[200px_1fr_auto] sm:items-end"
                >
                  <input type="hidden" name="member" value={r.member} />
                  <input type="hidden" name="hold_id" value={r.hold_id} />
                  <div>
                    <label className="label" htmlFor={`i-${r.hold_id}`}>
                      Instruction
                    </label>
                    <select
                      id={`i-${r.hold_id}`}
                      name="instruction"
                      className="field"
                      defaultValue="continue"
                    >
                      <option value="continue">Continue the hold</option>
                      <option value="release">Release the hold</option>
                    </select>
                  </div>
                  <div>
                    <label className="label" htmlFor={`a-${r.hold_id}`}>
                      Police station or officer
                    </label>
                    <input
                      id={`a-${r.hold_id}`}
                      name="authority"
                      required
                      minLength={3}
                      maxLength={200}
                      className="field"
                      defaultValue="Cyber Crime Police Station, Hyderabad"
                    />
                  </div>
                  <button className="button button-solid">Send instruction</button>
                </form>
              ) : (
                <p className="text-muted mt-4 text-sm">
                  {r.instruction
                    ? `Instruction recorded: ${r.instruction === "continue" ? "continue the hold" : "release the hold"}.`
                    : "Released."}
                </p>
              )}
            </article>
          ))}
        </div>
      )}
    </>
  );
}
