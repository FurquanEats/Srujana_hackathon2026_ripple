"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CaseQueue, TierCounts } from "@/components/CaseQueue";
import { LearnedPatterns } from "@/components/LearnPattern";
import { Button, Card, ConnectionStatus, DemoBadge, EmptyState, ErrorNote, Icon, Notice, PageHeader, RiskDot, Spinner, Stat } from "@/components/ui";
import { api, money, time, type CaseSummary, type InjectResult, type ScoredTransaction } from "@/lib/api";
import { reasonLabel } from "@/lib/labels";
import { useStream } from "@/lib/useStream";

const SCENARIOS: { kind: string; label: string; note: string }[] = [
  { kind: "digital_arrest", label: "Digital arrest", note: "A pensioner coached into emptying an FD" },
  { kind: "mule_ring", label: "Mule ring", note: "Seven victims, two mules, one collector" },
  { kind: "scam_fanout", label: "Scam fan-out", note: "One payment split seven ways" },
  { kind: "sim_swap_takeover", label: "SIM swap", note: "A new phone drains an account" },
  { kind: "cash_structuring", label: "Cash structuring", note: "Deposits kept under ₹50,000" },
  { kind: "diwali_spike", label: "Diwali shopping", note: "Honest spending. Should stay quiet" },
  { kind: "patient_ring", label: "Patient mule ring", note: "Built to slip past every rule" },
];

const fmtInt = (n: number) => Math.round(n).toLocaleString("en-IN");

function LiveFeed({ feed, connected }: { feed: ScoredTransaction[]; connected: boolean }) {
  const [paused, setPaused] = useState<ScoredTransaction[] | null>(null);
  const rows = paused ?? feed;
  return (
    <Card title="Payments" description="Newest first. Alerts stand out; the rest stay quiet."
          action={
            <Button size="sm" variant="secondary" onClick={() => setPaused(paused ? null : feed)} aria-pressed={paused !== null} disabled={feed.length === 0}>
              <Icon name={paused ? "play" : "pause"} className="h-4 w-4" />{paused ? "Resume" : "Pause"}
            </Button>
          }>
      {rows.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted">
          {connected ? <><Spinner /> Waiting for payments…</> : "The live stream is disconnected. Payments will appear when it reconnects."}
        </p>
      ) : (
        <ul className="-mx-1 max-h-[34rem] divide-y divide-line overflow-y-auto px-1" aria-label="Recent payments">
          {rows.map((t) => (
            <li key={t.txn_id} className={`py-2 ${t.is_alert ? "" : "text-muted"}`}>
              <div className="flex items-center gap-2">
                <RiskDot p={t.probability} />
                <span className="min-w-0 flex-1 truncate font-mono text-xs" title={`${t.src_account} to ${t.dst_account}`}>
                  {t.src_account} <span className="text-subtle">→</span> {t.dst_account}
                </span>
                <span className={`whitespace-nowrap text-sm tabular-nums ${t.is_alert ? "font-semibold text-ink" : ""}`}>{money(t.amount, t.currency)}</span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 pl-[18px] text-[11px] text-subtle">
                <time dateTime={t.ts}>{time(t.ts)}</time>
                <span>{t.rail}</span>
                {t.location && <span>{t.location}</span>}
                <span className="tabular-nums">score {t.probability.toFixed(2)}</span>
                {t.is_alert && (
                  <span className="inline-flex items-center gap-1 rounded bg-navy px-1.5 py-px font-semibold text-white">
                    <Icon name="critical" className="h-3 w-3" />Alert
                  </span>
                )}
                {t.is_alert && t.reasons[0] && <span className="text-muted">{reasonLabel(t.reasons[0].code)}</span>}
                {t.case_id && t.is_alert && (
                  <Link href={`/cases/${t.case_id}`} className="font-mono font-semibold text-link hover:underline">{t.case_id}</Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {paused && <p className="mt-2 text-xs text-subtle">Feed paused. New payments are still being scored; resume to see the latest.</p>}
    </Card>
  );
}

function DemoControls() {
  const [busy, setBusy] = useState<string | null>(null);
  const [injected, setInjected] = useState<InjectResult | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const inject = async (kind: string) => {
    setBusy(kind);
    setFailed(null);
    try {
      setInjected(await api.inject(kind));
    } catch (e) {
      setInjected(null);
      setFailed((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section aria-labelledby="demo-heading" className="no-print rounded-card border border-dashed border-line-strong p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="demo-heading" className="text-base font-semibold text-navy">Scenario injection</h2>
        <DemoBadge>Demo only</DemoBadge>
      </div>
      <p className="mt-1 text-sm text-muted">
        Drops synthetic payments into the live stream. Watch Ripple react.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-2 min-[420px]:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7">
        {SCENARIOS.map((s) => (
          <button key={s.kind} type="button" onClick={() => inject(s.kind)} disabled={busy !== null}
                  className="flex min-h-11 flex-col items-start rounded-xl border border-line bg-surface px-3.5 py-2.5 text-left hover:-translate-y-0.5 hover:border-navy disabled:cursor-not-allowed disabled:opacity-55">
            <span className="flex items-center gap-2 text-sm font-semibold text-ink">
              {busy === s.kind && <Spinner className="h-3.5 w-3.5" />}
              {busy === s.kind ? "Injecting…" : s.label}
            </span>
            <span className="text-xs text-muted">{s.note}</span>
          </button>
        ))}
      </div>
      {failed && <div className="mt-4"><ErrorNote title="Scenario not injected" error={failed} /></div>}
      {injected && (
        <Notice tone="success" className="mt-4" title={`Injected ${injected.txn_ids.length} synthetic payments (${injected.kind.replace(/_/g, " ")}) at ${time(injected.at)}.`}>
          {injected.victim_account ? (
            <>
              The simulated victim is <span className="font-mono font-semibold">{injected.victim_account}</span>.{" "}
              <Link className="font-semibold text-link underline" href={`/trace?account=${encodeURIComponent(injected.victim_account)}&from=${encodeURIComponent(injected.victim_paid_at ?? injected.at)}`}>
                Trace it now
              </Link>
            </>
          ) : "Watch the cases below."}
        </Notice>
      )}
    </section>
  );
}

export default function CommandCentre() {
  const { feed, stats, lastCase, connected, updatedAt } = useStream();
  const [budget, setBudget] = useState(20);
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.cases(budget).then((c) => { setCases(c); setError(null); }).catch((e) => setError(e.message));
  }, [budget]);

  useEffect(load, [load, lastCase]);

  const hasStats = Object.keys(stats).length > 0;
  const kpi = (v: number | undefined, f: (n: number) => string) => (hasStats && v != null ? f(v) : "—");

  return (
    <div className="space-y-6">
      <PageHeader title="Every payment, scored as it lands."
                  description="Linked alerts become cases, worst first. Open one to see why, where the money went, and what to hold."
                  actions={<ConnectionStatus connected={connected} warmingUp={Boolean(stats.warming_up)} updatedAt={updatedAt} />} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        <Stat label="Scored" value={kpi(stats.processed, fmtInt)} hint="payments since start" />
        <Stat label="Rate" value={kpi(stats.tps, (n) => `${fmtInt(n)}/s`)} hint="payments a second" />
        <Stat label="Latency" value={kpi(stats.p95_latency_ms, (n) => `${n.toFixed(2)} ms`)} hint="p95, per payment" />
        <Stat label="Alerts" value={kpi(stats.alerts, fmtInt)} hint="scored 0.60 or more" />
        <div className="col-span-2 sm:col-span-1">
          <Stat label="Open cases" value={hasStats && stats.open_cases != null ? fmtInt(stats.open_cases) : cases ? fmtInt(cases.length) : "—"}
                hint="waiting for an officer" />
        </div>
      </div>

      {error && <ErrorNote title="Ripple is not answering" error={error} onRetry={load} />}

      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Cases" className="xl:col-span-2"
              description={cases ? <TierCounts cases={cases} /> : undefined}
              action={
                <div className="w-full sm:w-auto">
                  <label htmlFor="budget" className="flex items-center justify-between gap-3 text-sm font-semibold text-ink">
                    Show top
                    <output htmlFor="budget" className="min-w-12 rounded bg-sunken px-2 py-0.5 text-right tabular-nums">{budget}</output>
                  </label>
                  <input id="budget" type="range" min={5} max={100} step={5} value={budget} className="mt-1 w-full sm:w-56"
                         onChange={(e) => setBudget(Number(e.target.value))} aria-describedby="budget-hint" />
                  <p id="budget-hint" className="text-xs text-subtle">Match it to your team&apos;s capacity</p>
                </div>
              }>
          {cases === null && !error ? (
            <p className="flex items-center gap-2 text-sm text-muted" role="status"><Spinner /> Loading cases…</p>
          ) : cases === null ? (
            <EmptyState icon="wifiOff" title="No connection">Cases appear as soon as Ripple is reachable.</EmptyState>
          ) : (
            <CaseQueue cases={cases ?? []} />
          )}
        </Card>

        <LiveFeed feed={feed} connected={connected} />
      </div>

      <LearnedPatterns />

      <DemoControls />

    </div>
  );
}
