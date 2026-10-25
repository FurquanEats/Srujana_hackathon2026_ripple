"use client";

import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, money, moneyShort, pct, time, type FreezeAction, type InterdictionPlan, type Lien } from "@/lib/api";

import { Button, Card, Dialog, EmptyState, Icon, Notice, ShowMore, Spinner, Stat } from "./ui";

const TOP_FREEZES = 5;

const RULE_LABEL = { haircut: "Haircut (pro rata)", fifo: "First in, first out", libr: "Lowest intermediate balance" } as const;

/** True when the tracing rules disagree by at least a rupee, so a range is worth showing. */
const hasRange = (low?: number | null, high?: number | null): low is number =>
  low != null && high != null && high - low >= 1;

/** The four headline figures: traced, recoverable now, escaped, recoverable at first alert. */
export function RecoveryMetrics({ plan, currency = "INR" }: { plan: InterdictionPlan; currency?: string }) {
  const share = plan.stolen ? plan.recoverable_now / plan.stolen : 0;
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 lg:grid-cols-4">
      <Stat icon="search" label="Traced from victims" value={money(plan.stolen, currency)}
            hint={`from ${plan.victims.length} source account${plan.victims.length === 1 ? "" : "s"}`} />
      <Stat icon="lock" label="Recoverable now" value={money(plan.recoverable_now, currency)} tone="good" emphasis
            hint={hasRange(plan.recoverable_low, plan.recoverable_high)
              ? `${money(plan.recoverable_low, currency)} to ${money(plan.recoverable_high!, currency)} across three tracing rules`
              : `${pct(share)} of traced money, held by the recommended accounts`} />
      <Stat icon="critical" label="Already escaped" value={money(plan.escaped, currency)} tone={plan.escaped > 0 ? "bad" : "default"}
            hint="to cash, crypto or out of Ripple's view" />
      <Stat icon="clock" label="Recoverable at first alert"
            value={plan.recoverable_share_at_first_alert != null ? pct(plan.recoverable_share_at_first_alert) : "Not available"}
            hint={plan.first_alert_at
              ? <>alert at {time(plan.first_alert_at)}{plan.recoverable_at_first_alert != null && <> · {money(plan.recoverable_at_first_alert, currency)}</>}</>
              : "no alert in this trail"} />
    </div>
  );
}

/** The race between the alert and the cash-out: traced money still inside the trail vs. money that has left. */
export function RecoveryChart({ plan, currency = "INR", embedded = false }: { plan: InterdictionPlan; currency?: string; embedded?: boolean }) {
  if (plan.timeline.length < 2) {
    return embedded ? null : (
      <Card title="Recoverable money over time">
        <EmptyState icon="clock" title="Not enough history to chart">The trail has fewer than two points in time.</EmptyState>
      </Card>
    );
  }
  const data = plan.timeline.map((p) => ({ ...p, t: new Date(p.ts).getTime() }));
  const first = plan.timeline[0];
  const last = plan.timeline[plan.timeline.length - 1];
  const tick = (t: number) => new Date(t).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

  const chart = (
    <figure className="m-0">
      <div className="h-64 sm:h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 24, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e3eaf2" vertical={false} />
            <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time" tickFormatter={tick}
                   stroke="#5d6d84" fontSize={11} tickMargin={6} minTickGap={40} />
            <YAxis stroke="#5d6d84" fontSize={11} tickFormatter={(v) => moneyShort(Number(v), currency)} width={64} />
            <Tooltip labelFormatter={(t) => time(new Date(Number(t)).toISOString())}
                     formatter={(v) => money(Number(v), currency)}
                     contentStyle={{ background: "#fff", border: "1px solid #d6e0eb", borderRadius: 8, fontSize: 12, color: "#13233d" }} />
            <Legend wrapperStyle={{ fontSize: 12, color: "#4a5b73" }} />
            <Area isAnimationActive={false} type="stepAfter" dataKey="recoverable" name="Still in the trail (recoverable)" stroke="#0f6b4f" strokeWidth={2} fill="#0f6b4f" fillOpacity={0.14} />
            <Area isAnimationActive={false} type="stepAfter" dataKey="escaped" name="Escaped to cash or crypto" stroke="#b42332" strokeWidth={2} strokeDasharray="6 3" fill="#b42332" fillOpacity={0.08} />
            {plan.first_alert_at && (
              <ReferenceLine x={new Date(plan.first_alert_at).getTime()} stroke="#0b1f3a" strokeDasharray="4 4"
                             label={{ value: "Ripple alert", fill: "#0b1f3a", fontSize: 11, fontWeight: 600, position: "insideTopLeft" }} />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-2 text-xs text-muted">
        At {time(first.ts)}, {money(first.recoverable, currency)} was in the trail. By {time(last.ts)},{" "}
        {money(last.recoverable, currency)} remained recoverable and {money(last.escaped, currency)} had escaped.
      </figcaption>
    </figure>
  );

  return embedded ? chart : (
    <Card title="Recoverable money over time" description="Every minute counts: money leaves the trail as mules cash out.">
      {chart}
    </Card>
  );
}

/** The structured lien requests for holds at other banks, in the fields a CFCFRMS lien request carries. */
function cfcfrmsExport(plan: InterdictionPlan, holds: FreezeAction[]) {
  const evidence = (account: string) => plan.edges.filter((e) => e.target === account || e.source === account)
    .map((e) => ({ txn_id: e.txn_id, at: e.ts, from: e.source, to: e.target, amount: e.amount }));
  return {
    format: "ripple.cfcfrms-lien-request/1",
    generated_at: new Date().toISOString(),
    reference: plan.case_id,
    victims: plan.victims,
    traced_total: plan.stolen,
    escaped: plan.escaped,
    requests: holds.map((f) => ({
      account: f.account_id,
      bank: f.bank,
      action: "lien on the traced amount only; the rest of the account stays usable",
      amount: f.hold_low ?? f.recoverable,
      range_across_tracing_rules: { low: f.hold_low ?? f.recoverable, high: f.hold_high ?? f.recoverable, by_rule: f.by_rule ?? {} },
      reason: f.reason,
      evidence: evidence(f.account_id),
    })),
    note: "Prepared by Ripple for an officer to review and submit through CFCFRMS. Not a legal determination.",
  };
}

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

/** Ranked liens on the traced amount. This bank's accounts get a lien placed in one step, after the officer confirms;
 *  accounts at other banks go out together as a CFCFRMS request. */
export function FreezeList({ plan, currency = "INR" }: { plan: InterdictionPlan; currency?: string }) {
  const [liens, setLiens] = useState<Record<string, Lien>>({});
  const [confirm, setConfirm] = useState<FreezeAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const shown = all ? plan.freeze : plan.freeze.slice(0, TOP_FREEZES);
  const external = plan.freeze.filter((f) => f.own_bank === false);

  useEffect(() => {
    api.liens(plan.case_id)
      .then((ls) => setLiens(Object.fromEntries(ls.filter((l) => l.status === "placed").map((l) => [l.account_id, l]))))
      .catch(() => setLiens({}));
  }, [plan.case_id]);

  const place = async () => {
    if (!confirm) return;
    setBusy(true);
    setError(null);
    try {
      const lien = await api.placeLien(plan.case_id, confirm.account_id, confirm.hold_low ?? confirm.recoverable);
      setLiens((l) => ({ ...l, [lien.account_id]: lien }));
      setConfirm(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title={`Recommended holds · ${plan.freeze.length} account${plan.freeze.length === 1 ? "" : "s"}`}
          description="Each is a lien on the traced amount only; the rest of the account stays usable. Ranked by money recovered."
          action={external.length > 0 && (
            <Button size="sm" variant="secondary" onClick={() => download(`cfcfrms-${plan.case_id}.json`, cfcfrmsExport(plan, external))}>
              <Icon name="draft" className="h-4 w-4" /> Export for CFCFRMS ({external.length})
            </Button>
          )}>
      {plan.freeze.length === 0 ? (
        <EmptyState icon="lock" title="Nothing left to hold">The traced money has already left the accounts Ripple can see.</EmptyState>
      ) : (
        <>
          <ol id="freeze-list" className="space-y-3">
            {shown.map((f, i) => {
              const lien = liens[f.account_id];
              return (
                <li key={f.account_id} className="rounded-lg border border-line bg-surface p-3 sm:p-4">
                  <div className="flex items-start gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy text-sm font-bold text-white" aria-label={`Rank ${i + 1}`}>
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        <span className="whitespace-nowrap font-mono text-sm font-semibold text-ink">{f.account_id}</span>
                        <span className="whitespace-nowrap rounded bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-muted">{f.bank ?? "Bank unknown"}</span>
                        {lien && (
                          <span className="inline-flex items-center gap-1 whitespace-nowrap rounded bg-teal-soft px-1.5 py-0.5 text-[11px] font-semibold text-teal-strong">
                            <Icon name="lock" className="h-3 w-3" /> Lien placed · {money(lien.amount, currency)} · {time(lien.placed_at)}
                          </span>
                        )}
                      </div>
                      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:flex sm:flex-wrap sm:gap-x-6">
                        <div>
                          <dt className="text-xs text-subtle">Traced amount held</dt>
                          <dd className="font-semibold tabular-nums text-recover">{money(f.recoverable, currency)}</dd>
                        </div>
                        {hasRange(f.hold_low, f.hold_high) && (
                          <div>
                            <dt className="text-xs text-subtle">Across three tracing rules</dt>
                            <dd className="tabular-nums text-ink"
                                title={(Object.keys(RULE_LABEL) as (keyof typeof RULE_LABEL)[]).map((r) => `${RULE_LABEL[r]}: ${money(f.by_rule?.[r] ?? 0, currency)}`).join(" · ")}>
                              {money(f.hold_low, currency)} to {money(f.hold_high!, currency)}
                            </dd>
                          </div>
                        )}
                        <div>
                          <dt className="text-xs text-subtle">Disruption score</dt>
                          <dd className="tabular-nums text-ink">{f.collateral_cost.toFixed(1)} <span className="text-xs text-subtle">lower is less disruptive</span></dd>
                        </div>
                      </dl>
                      <p className="mt-2 text-sm text-muted">{f.reason}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
                    {f.own_bank ? (
                      lien ? null : (
                        <Button size="sm" variant="primary" onClick={() => { setError(null); setConfirm(f); }}
                                aria-label={`Place lien on ${f.account_id}`}>
                          <Icon name="lock" className="h-4 w-4" /> Place lien
                        </Button>
                      )
                    ) : (
                      <span className="text-xs text-subtle">At {f.bank}: goes out in the CFCFRMS export</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          <ShowMore expanded={all} hidden={plan.freeze.length - TOP_FREEZES} onToggle={() => setAll((a) => !a)} noun="accounts" controls="freeze-list" />
        </>
      )}
      <p className="mt-4 text-xs text-subtle">Method: {plan.method}.</p>

      <Dialog open={confirm !== null} onClose={() => setConfirm(null)}
              title={<>Place a lien on <span className="font-mono">{confirm?.account_id}</span></>}
              description="The lien covers the traced amount only. The account holder can still use the rest."
              footer={
                <>
                  <Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
                  <Button variant="primary" onClick={place} disabled={busy}>
                    {busy ? <Spinner /> : <Icon name="lock" className="h-4 w-4" />} Place lien of {confirm ? money(confirm.hold_low ?? confirm.recoverable, currency) : ""}
                  </Button>
                </>
              }>
        {confirm && hasRange(confirm.hold_low, confirm.hold_high) && (
          <p className="text-sm text-muted">The three tracing rules give {money(confirm.hold_low, currency)} to {money(confirm.hold_high!, currency)}. The lien uses the lowest, which every rule supports.</p>
        )}
        {error && <div className="mt-3"><Notice tone="warning" title="Lien not placed">{error}</Notice></div>}
      </Dialog>
    </Card>
  );
}

/** Where the traced money is, the holds that recover the most of it, and the race between alert and cash-out. */
export function FreezePlan({ plan, currency = "INR" }: { plan: InterdictionPlan; currency?: string }) {
  return (
    <div className="space-y-6">
      <RecoveryMetrics plan={plan} currency={currency} />
      <FreezeList plan={plan} currency={currency} />
      {plan.timeline.length > 1 && <RecoveryChart plan={plan} currency={currency} />}
    </div>
  );
}
