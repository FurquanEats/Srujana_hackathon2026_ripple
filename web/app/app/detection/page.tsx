import type { Metadata } from "next";

import { Notice, PageHeader, Stat } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { LIVE, shadowRun, thresholdHistory, thresholds } from "@/lib/gateway/source";
import type { Thresholds } from "@/lib/gateway/types";
import { requireRole } from "@/lib/guard";

import { approveThresholds } from "../actions";

export const metadata: Metadata = { title: "Detection" };

/** Each rule's knob, how the shadow run names it, and its unit. */
const KNOBS: { field: keyof Thresholds; rule: string; label: string; unit: string; step: string }[] = [
  {
    field: "pass_through_minutes",
    rule: "pass_through",
    label: "Pass-through window",
    unit: "minutes",
    step: "1",
  },
  {
    field: "new_senders",
    rule: "many_new_senders",
    label: "New senders in a day",
    unit: "senders",
    step: "1",
  },
  {
    field: "profile_multiple",
    rule: "out_of_profile",
    label: "Credits over declared income",
    unit: "times",
    step: "0.1",
  },
  {
    field: "dormant_days",
    rule: "dormant_then_busy",
    label: "Dormant for at least",
    unit: "days",
    step: "1",
  },
  {
    field: "cash_out_minutes",
    rule: "quick_cash_out",
    label: "Quick cash-out window",
    unit: "minutes",
    step: "1",
  },
];

export default async function DetectionPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; done?: string; budget?: string }>;
}) {
  const session = await requireRole("frm_analyst");
  const { error, done, budget } = await searchParams;
  const perDay = Math.min(10_000, Math.max(0.5, Number(budget) || 5));
  const [current, run, history] = await Promise.all([
    thresholds(session),
    shadowRun(session, perDay),
    thresholdHistory(session),
  ]);
  const proposal = run?.proposal ?? current;
  return (
    <>
      <PageHeader
        title="Detection thresholds"
        lead="Ripple replays the last 30 days of this bank's postings at a range of settings for each rule, and proposes the most sensitive settings that stay within the number of flags your team can review in a day. No model is trained: the rules are fixed, only their thresholds move, and you approve every change."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}

      {run ? (
        <>
          <div className="mb-8 grid gap-3 sm:grid-cols-4">
            <Stat label="Accounts replayed">{run.accounts}</Stat>
            <Stat label="Known bad in the window">{run.known_bad}</Stat>
            <Stat label="Expected flags per day">{run.expected_flags_per_day}</Stat>
            <Stat label="Review budget per day">{run.budget_per_day}</Stat>
          </div>
          <form className="mb-8 flex flex-wrap items-end gap-3" method="get">
            <div>
              <label htmlFor="budget" className="label">
                Flags your team can review per day
              </label>
              <input
                id="budget"
                name="budget"
                type="number"
                min="0.5"
                step="0.5"
                defaultValue={perDay}
                className="field w-40"
              />
            </div>
            <button
              className="button button-ghost"
              disabled={!LIVE}
              title={LIVE ? undefined : "Saved data has one shadow run, at 5 a day"}
            >
              Run the shadow run again
            </button>
            {typeof run.since === "string" && typeof run.until === "string" && (
              <p className="text-faint text-xs">
                Replayed {formatIst(run.since)} to {formatIst(run.until)}.
              </p>
            )}
          </form>

          <section aria-labelledby="tradeoffs" className="mb-10">
            <h2 id="tradeoffs" className="pixel mb-4 text-lg">
              The trade-off, rule by rule
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              {run.rules.map((rule) => (
                <div key={rule.rule} className="border-line min-w-0 border p-4">
                  <p className="text-fg mb-3 text-sm">{rule.title}</p>
                  <div className="overflow-x-auto">
                    <table className="table min-w-[360px]">
                      <thead>
                        <tr>
                          <th>Setting</th>
                          <th className="text-right">Accounts flagged</th>
                          <th className="text-right">Flags a day</th>
                          <th className="text-right">Known bad caught</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rule.rows.map((row) => (
                          <tr key={row.value} className={row.value === rule.chosen ? "bg-hover" : ""}>
                            <td className="font-mono">
                              {row.value}
                              {row.value === rule.chosen && (
                                <span className="ml-2 bg-accent px-1 font-sans text-[11px] text-ink">
                                  proposed
                                </span>
                              )}
                            </td>
                            <td className="text-right font-mono">{row.accounts_flagged}</td>
                            <td className="text-right font-mono">{row.flags_per_day}</td>
                            <td className="text-right font-mono">{row.known_bad_flagged}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : (
        <Notice kind="error">This institution has too little history for a shadow run.</Notice>
      )}

      <section aria-labelledby="approve" className="border-line border p-5">
        <h2 id="approve" className="pixel mb-1 text-lg">
          Approve thresholds
        </h2>
        <p className="text-muted mb-5 text-[13px]">
          The form starts from the proposal. The current setting is shown under each field.
        </p>
        <form action={approveThresholds} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <input type="hidden" name="budget_per_day" value={perDay} />
          {KNOBS.map((k) => (
            <div key={k.field}>
              <label htmlFor={k.field} className="label">
                {k.label} ({k.unit})
              </label>
              <input
                id={k.field}
                name={k.field}
                type="number"
                min="0"
                step={k.step}
                required
                defaultValue={proposal[k.field]}
                className="field"
              />
              <p className="text-faint mt-1 text-xs">Now {current[k.field]}</p>
            </div>
          ))}
          <div className="flex items-end">
            <button className="button button-solid">Approve and apply</button>
          </div>
        </form>
      </section>
      <section className="mt-10">
        <h2 className="pixel mb-3 text-lg">Approval history</h2>
        {history.length === 0 ? (
          <p className="text-muted text-sm">
            No settings approved yet: the rules run at Ripple&apos;s defaults.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="table min-w-[720px]">
              <thead>
                <tr>
                  <th>Approved</th>
                  <th>By</th>
                  {KNOBS.map((k) => (
                    <th key={k.field}>{k.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.approved_at}>
                    <td className="text-muted text-xs whitespace-nowrap">{formatIst(h.approved_at)}</td>
                    <td className="font-mono text-xs">{h.approved_by}</td>
                    {KNOBS.map((k) => (
                      <td key={k.field} className="font-mono">
                        {h.settings[k.field]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
