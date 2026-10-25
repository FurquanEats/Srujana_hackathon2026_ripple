"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Button, Card, EmptyState, ErrorNote, Icon, LoadingPanel, Notice, PageHeader, Stat } from "@/components/ui";
import { api, money, pct, time, type ConsortiumReport, type EvalReport, type MetricRow, type OneShotIbmReport, type OneShotReport, type RedTeamRun } from "@/lib/api";

const AXIS = { stroke: "#6d7076", fontSize: 11 };
const GRID = "#ece9e1";
const tooltip = { contentStyle: { background: "#fff", border: "1px solid #e4e1d8", borderRadius: 8, fontSize: 12, color: "#15171a" } };
const C = { precision: "#3a3e44", recall: "#0b6e63", value: "#a35f00" };

// Notes that say the figures are not final measured results. Matched, never invented: the note text is shown verbatim.
const WIP = /\b(illustrative|sample data|not measured|preliminary|work in progress|placeholder)\b/i;
const SAMPLE_DATASET = /\(sample\)/i;

const points = (a: number, b: number) => {
  const d = Math.round((a - b) * 100);
  return `${d >= 0 ? "+" : "−"}${Math.abs(d)} pts`;
};

function Table({ caption, head, children }: { caption: string; head: ReactNode; children: ReactNode }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="border-b border-line text-xs text-muted">{head}</thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}
const th = "py-2 pr-3 font-semibold";
const td = "py-2.5 pr-3 tabular-nums";

function Headline({ o, b, report }: { o: MetricRow; b: MetricRow; report: EvalReport }) {
  return (
    <section aria-labelledby="headline" className="print-break-avoid">
      <h2 id="headline" className="mb-3 text-base font-semibold text-navy">Headline results · Ripple against a single-transaction rule</h2>
      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4">
        <Stat emphasis label="Precision" value={pct(o.precision)} tone="accent"
              hint={<>Rule: {pct(b.precision)} · <span className="font-semibold text-ink">{points(o.precision, b.precision)}</span></>} />
        <Stat emphasis label="Recall" value={pct(o.recall)} tone="accent"
              hint={<>Rule: {pct(b.recall)} · <span className="font-semibold text-ink">{points(o.recall, b.recall)}</span></>} />
        <Stat emphasis label="PR-AUC" value={o.pr_auc != null ? o.pr_auc.toFixed(2) : "Not reported"} tone="accent"
              hint={b.pr_auc != null ? <>Rule: {b.pr_auc.toFixed(2)}</> : "No baseline figure"} />
        <Stat emphasis label="Throughput" value={report.throughput_tps ? `${Math.round(report.throughput_tps).toLocaleString("en-IN")}/s` : "Not reported"}
              hint={report.p95_latency_ms ? `p95 ${report.p95_latency_ms} ms per payment` : "payments scored per second"} />
      </div>
    </section>
  );
}

function RedTeam({ redteam }: { redteam: { latest: RedTeamRun; before: RedTeamRun | null } }) {
  const r = redteam.latest;
  return (
    <Card title="Red team: an attacker that learns"
          description={`Run ${time(r.generated_at)} · ${r.plans_tried} laundering plans tried`}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {redteam.before && <Stat label="Evading plans before the fix" value={redteam.before.evading_plans} hint={`of ${redteam.before.plans_tried} tried`} />}
        <Stat label="Evading plans now" value={r.evading_plans} hint={`of ${r.plans_tried} tried`} tone={r.evading_plans > 0 ? "bad" : "default"} />
        <Stat label="Plans caught" value={pct(r.caught_share)} hint="some payment reached Review or Critical" tone="good" />
      </div>
      <h3 className="mt-5 text-sm font-semibold text-ink">Remaining blind spots · what to fix next</h3>
      {r.blind_spots.length === 0 ? <p className="mt-1 text-sm text-muted">None found in this run.</p> : (
        <ul className="mt-2 divide-y divide-line rounded-lg border border-line">
          {r.blind_spots.slice(0, 4).map((s) => (
            <li key={s.description} className="flex flex-col gap-1 px-3 py-2.5 text-sm sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
              <span className="text-ink">{s.description}</span>
              <span className="whitespace-nowrap tabular-nums text-muted">{money(s.laundered)} moved · top score {s.max_probability.toFixed(2)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-subtle">{r.note}</p>
    </Card>
  );
}

function OneShot({ r }: { r: OneShotReport }) {
  const g = r.generalisation;
  const a = r.adaptive_red_team;
  const u = r.unseen_bank;
  return (
    <Card title="One-shot learning: one missed scam in, one new detector out"
          description={`One trail the engine let through (${r.example.plan}; top score ${r.example.peak_probability.toFixed(2)}, below Review) was the only example. Run ${time(r.generated_at)}.`}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat label="Missed plans now caught" value={`${g.of_missed_caught_with} of ${g.missed_without}`} tone="good"
              hint={`random laundering plans the engine missed, out of ${g.plans} tried`} />
        <Stat label="Adaptive red team: evading plans" value={`${a.without.evading_plans} → ${a.with.evading_plans}`} tone="good"
              hint={`of ${a.with.plans_tried} plans an adaptive attacker tried`} />
        <Stat label="False alarms on an unseen bank" value={u.with.motif_alerts_on_legit}
              hint={`legitimate payments it flagged in ${u.days} days of a bank it never saw (${u.transactions.toLocaleString("en-IN")} payments)`} />
      </div>
      <h3 className="mt-5 text-sm font-semibold text-ink">What Ripple learned: &ldquo;{r.motif.name}&rdquo;</h3>
      <ul className="mt-2 divide-y divide-line rounded-lg border border-line">
        {r.motif.constraints.map((c) => (
          <li key={c.feature} className="flex flex-col gap-1 px-3 py-2.5 text-sm sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
            <span className="text-ink">{c.text}</span>
            <span className="whitespace-nowrap tabular-nums text-muted">{pct(c.background_share, 1)} of ordinary relay payments meet this alone</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-sm text-muted">
        Ripple freed the amount, the waits, the split and the number of hops, because a criminal changes those between runs. What it kept
        describes the accounts, which are much harder to change. It checked the result against {r.motif.background_events.toLocaleString("en-IN")} ordinary
        payments over {r.motif.background_days} days before it could go live.
      </p>
      {r.notes.map((n) => <p key={n} className="mt-1 text-xs text-subtle">{n}</p>)}
    </Card>
  );
}

const typeName = (t: string) => t.replace(/_/g, "-").toUpperCase();

function OneShotIbm({ r }: { r: OneShotIbmReport }) {
  const learned = r.per_type.filter((t) => !t.error);
  return (
    <Card title="Where one-shot learning does not work yet: IBM AML"
          description={`${r.dataset}, ${r.rows.toLocaleString("en-IN")} payments over ${r.days} days. Run ${time(r.generated_at)}.`}>
      <Table caption="One-shot learning per IBM laundering type"
             head={<tr><th className={th}>Type</th><th className={th}>Later attempts caught</th><th className={th}>In time to act</th><th className={th}>Legitimate matches a day</th><th className={th}>What it learned</th></tr>}>
        {r.per_type.map((t) => (
          <tr key={t.type} className="align-top">
            <td className={`${td} font-semibold text-ink`}>{typeName(t.type)}</td>
            {t.error ? (
              <td className={`${td} text-muted`} colSpan={4}>Not learnable from this example: {t.error}</td>
            ) : (
              <>
                <td className={td}>{t.caught_same_type} of {t.attempts_after}{t.attempts_after ? ` (${pct((t.caught_same_type ?? 0) / t.attempts_after)})` : ""}</td>
                <td className={td}>{t.caught_same_type_in_time} of {t.attempts_after}</td>
                <td className={td}>{t.legit_matches_per_day}</td>
                <td className="py-2.5 pr-3 text-xs text-muted">{t.rules?.join("; ")}</td>
              </>
            )}
          </tr>
        ))}
      </Table>
      <p className="mt-3 text-sm text-muted">
        One-shot learning describes the accounts that pass money on. In the Indian simulator those are fresh accounts with no spending of their own,
        which ordinary customers almost never resemble. IBM&apos;s synthetic laundering hides inside ordinary, long-lived accounts, and its types are
        defined by the shape of the graph (a stack, a cycle), so one attempt&apos;s account traits do not carry over to the next: within a type, the
        accounts&apos; own spending ranges from none to dozens of payments and the money waits anywhere from two hours to two days. Learning
        graph shapes from one example is the next step. {learned.length} of {r.per_type.length} types could be learned from a single attempt. Each pattern was allowed at most {r.max_false_alarms_per_day} false alarms a day,
        judged only on traffic seen before it went live.
      </p>
      {r.notes.map((n) => <p key={n} className="mt-1 text-xs text-subtle">{n}</p>)}
    </Card>
  );
}

export default function Evaluation() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consortium, setConsortium] = useState<ConsortiumReport | null>(null);
  const [redteam, setRedteam] = useState<{ latest: RedTeamRun; before: RedTeamRun | null } | null>(null);
  const [oneshot, setOneshot] = useState<OneShotReport | null>(null);
  const [oneshotIbm, setOneshotIbm] = useState<OneShotIbmReport | null>(null);

  const load = useCallback(() => {
    api.eval().then(setReport).catch((e) => setError(e.message));
    api.consortium().then(setConsortium).catch(() => setConsortium(null));
    api.redteam().then(setRedteam).catch(() => setRedteam(null));
    api.oneshot().then(setOneshot).catch(() => setOneshot(null));
    api.oneshotIbm().then(setOneshotIbm).catch(() => setOneshotIbm(null));
  }, []);

  useEffect(load, [load]);

  if (error) return <ErrorNote title="Could not load the evaluation" error={error} onRetry={() => { setError(null); load(); }} />;
  if (!report) return <LoadingPanel label="Loading evaluation…" />;

  const o = report.overall;
  const b = report.baseline;
  const wipNotes = report.notes.filter((n) => WIP.test(n));
  const isWip = wipNotes.length > 0 || SAMPLE_DATASET.test(report.dataset);

  return (
    <article className="space-y-6">
      <PageHeader title="Does it work? The numbers."
                  description={<>{report.dataset} · {report.split}</>}
                  eyebrow={<span className="text-subtle">Report generated {time(report.generated_at)}</span>}
                  actions={
                    <Button variant="secondary" className="no-print" onClick={() => window.print()}>
                      <Icon name="printer" className="h-4 w-4" /> Print report
                    </Button>
                  } />

      {isWip && (
        <Notice tone="warning" title="Work in progress: not final measured results">
          {wipNotes.length > 0 ? wipNotes.map((n) => <p key={n}>{n}</p>) : <p>The dataset is marked as a sample.</p>}
        </Notice>
      )}

      <Headline o={o} b={b} report={report} />

      <Card title="Money still there at the first alert"
            description="Share of each laundering attempt's money still in the trail at the first alert. Never-alerted attempts count as zero.">
        {report.money_recoverable && report.money_recoverable.length > 0 ? (
          <Table caption="Money recoverable at first alert, by system"
                 head={<tr><th scope="col" className={th}>System</th><th scope="col" className={`${th} text-right`}>Attempts</th><th scope="col" className={`${th} text-right`}>Alerted</th><th scope="col" className={`${th} text-right`}>Median recoverable</th><th scope="col" className={`${th} text-right`}>Mean recoverable</th></tr>}>
            {report.money_recoverable.map((r) => (
              <tr key={r.name}>
                <th scope="row" className="py-2.5 pr-3 font-medium text-ink">{r.name}</th>
                <td className={`${td} text-right`}>{r.attempts.toLocaleString("en-IN")}</td>
                <td className={`${td} text-right`}>{pct(r.alerted_share)}</td>
                <td className={`${td} text-right font-semibold`}>{pct(r.median_recoverable)}</td>
                <td className={`${td} text-right`}>{pct(r.mean_recoverable)}</td>
              </tr>
            ))}
          </Table>
        ) : (
          <EmptyState icon="clock" title="Not in this report yet">
            This evaluation run did not include the recoverable-at-first-alert measurement.
          </EmptyState>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="What each layer adds (ablation)" description="Precision and recall as each layer is added to the detectors.">
          <figure className="m-0">
            <div className="h-80">
              <ResponsiveContainer>
                <BarChart data={report.ablation} layout="vertical" margin={{ left: 0, right: 16 }} barGap={2}>
                  <CartesianGrid stroke={GRID} horizontal={false} />
                  <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => pct(v)} {...AXIS} />
                  <YAxis type="category" dataKey="name" width={150} {...AXIS} tick={{ fontSize: 11, fill: "#15171a" }} />
                  <Tooltip formatter={(v) => pct(Number(v), 1)} {...tooltip} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar isAnimationActive={false} dataKey="precision" name="Precision" fill={C.precision} radius={[0, 3, 3, 0]} />
                  <Bar isAnimationActive={false} dataKey="recall" name="Recall" fill={C.recall} radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <figcaption className="mt-2 text-xs text-muted">
              From {report.ablation[0]?.name ?? "the first variant"} to {report.ablation[report.ablation.length - 1]?.name ?? "the full system"}.
            </figcaption>
          </figure>
        </Card>

        <Card title="Alert budget" description={`How much is caught at each daily alert budget. Suggested: ${report.suggested_budget} alerts a day.`}>
          <figure className="m-0">
            <div className="h-80">
              <ResponsiveContainer>
                <LineChart data={report.budget_curve} margin={{ top: 16, right: 16, bottom: 16 }}>
                  <CartesianGrid stroke={GRID} />
                  <XAxis dataKey="alerts_per_day" type="number" domain={["dataMin", "dataMax"]} {...AXIS}
                         label={{ value: "Alerts per day", position: "insideBottom", offset: -10, fill: "#55585e", fontSize: 11 }} />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v)} {...AXIS} width={44} />
                  <Tooltip formatter={(v) => pct(Number(v), 1)} labelFormatter={(l) => `${l} alerts per day`} {...tooltip} />
                  <Legend verticalAlign="top" wrapperStyle={{ fontSize: 12, paddingBottom: 8 }} />
                  <ReferenceLine x={report.suggested_budget} stroke="#15171a" strokeDasharray="4 4"
                                 label={{ value: "Suggested", fill: "#15171a", fontSize: 11, fontWeight: 600, position: "insideTopRight" }} />
                  <Line isAnimationActive={false} dataKey="recall" name="Laundering caught" stroke={C.recall} strokeWidth={2.5} dot={{ r: 3, strokeDasharray: "0" }} />
                  <Line isAnimationActive={false} dataKey="value_caught_share" name="Value caught" stroke={C.value} strokeWidth={2.5} strokeDasharray="6 3" dot={{ r: 3, strokeDasharray: "0" }} />
                  <Line isAnimationActive={false} dataKey="precision" name="Precision" stroke={C.precision} strokeWidth={2.5} strokeDasharray="2 3" dot={{ r: 3, strokeDasharray: "0" }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <figcaption className="mt-2 text-xs text-muted">Line styles differ as well as colours: solid caught, dashed value, dotted precision.</figcaption>
          </figure>
        </Card>
      </div>

      {redteam && <RedTeam redteam={redteam} />}

      {oneshot && <OneShot r={oneshot} />}

      {oneshotIbm && <OneShotIbm r={oneshotIbm} />}

      {consortium && (
        <Card title={`Bank consortium: ${consortium.member_banks.length} banks sharing only keyed hashes`}
              description={`${consortium.dataset}, ${consortium.rows.toLocaleString("en-IN")} payments.`}>
          <Table caption="Consortium results by sharing mode"
                 head={<tr><th scope="col" className={th}>Mode</th><th scope="col" className={`${th} text-right`}>Laundering payments</th><th scope="col" className={`${th} text-right`}>Caught</th><th scope="col" className={`${th} text-right`}>Recall</th><th scope="col" className={`${th} text-right`}>Alerts</th><th scope="col" className={`${th} text-right`}>Precision</th></tr>}>
            {consortium.results.map((r) => (
              <tr key={r.mode}>
                <th scope="row" className="py-2.5 pr-3 font-medium text-ink">{r.mode}</th>
                <td className={`${td} text-right`}>{r.laundering_payments.toLocaleString("en-IN")}</td>
                <td className={`${td} text-right`}>{r.caught.toLocaleString("en-IN")}</td>
                <td className={`${td} text-right`}>{r.recall != null ? pct(r.recall, 1) : "n/a"}</td>
                <td className={`${td} text-right`}>{r.alerts.toLocaleString("en-IN")}</td>
                <td className={`${td} text-right`}>{r.precision != null ? pct(r.precision, 1) : "n/a"}</td>
              </tr>
            ))}
          </Table>
          <p className="mt-3 text-xs text-subtle">{consortium.note}</p>
        </Card>
      )}

      <Card title="By laundering pattern" description="Each row is scored by the detector aimed at that pattern.">
        <Table caption="Precision and recall by laundering pattern"
               head={<tr><th scope="col" className={th}>Pattern</th><th scope="col" className={`${th} text-right`}>Precision</th><th scope="col" className={`${th} text-right`}>Recall</th><th scope="col" className={`${th} w-1/3`}><span className="sr-only">Recall bar</span></th></tr>}>
          {report.per_typology.map((r) => (
            <tr key={r.name}>
              <th scope="row" className="py-2.5 pr-3 font-medium capitalize text-ink">{r.name}</th>
              <td className={`${td} text-right`}>{pct(r.precision)}</td>
              <td className={`${td} text-right`}>{pct(r.recall)}</td>
              <td className="py-2.5" aria-hidden>
                <span className="block h-2 rounded-full bg-sunken"><span className="block h-full rounded-full bg-teal" style={{ width: pct(r.recall) }} /></span>
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card title="Limits, stated plainly">
        {report.notes.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink">{report.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        ) : <p className="text-sm text-muted">No notes were attached to this report.</p>}
        <dl className="mt-4 grid gap-x-6 gap-y-2 border-t border-line pt-4 text-sm sm:grid-cols-2">
          <div><dt className="text-xs text-subtle">Dataset</dt><dd className="text-ink">{report.dataset}</dd></div>
          <div><dt className="text-xs text-subtle">Split</dt><dd className="text-ink">{report.split}</dd></div>
          <div><dt className="text-xs text-subtle">Baseline</dt><dd className="text-ink">{b.name}</dd></div>
          <div><dt className="text-xs text-subtle">Generated</dt><dd className="text-ink">{time(report.generated_at)}</dd></div>
        </dl>
      </Card>
    </article>
  );
}
