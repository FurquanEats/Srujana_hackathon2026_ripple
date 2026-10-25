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
  { kind: "digital_arrest", label: "Digital arrest", note: "Coerced transfer, then a mule chain" },
  { kind: "mule_ring", label: "Mule ring", note: "Many accounts funnelling to collectors" },
  { kind: "scam_fanout", label: "Scam fan-out", note: "One payment split across mules" },
  { kind: "sim_swap_takeover", label: "SIM-swap takeover", note: "New device drains an account" },
  { kind: "cash_structuring", label: "Cash structuring", note: "Deposits kept under ₹50,000" },
  { kind: "diwali_spike", label: "Diwali shopping", note: "Legitimate spike; should stay quiet" },
  { kind: "patient_ring", label: "Patient mule ring", note: "Waits hours to a day per hop; no built-in detector acts" },
];

const fmtInt = (n: number) => Math.round(n).toLocaleString("en-IN");

function LiveFeed({ feed, connected }: { feed: ScoredTransaction[]; connected: boolean }) {
  const [paused, setPaused] = useState<ScoredTransaction[] | null>(null);
  const rows = paused ?? feed;
  return (
    <Card title="Live payments" description="Newest first. Alerts are marked; other payments stay quiet."
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
    <section aria-labelledby="demo-heading" className="no-print rounded-card border-2 border-dashed border-line-strong bg-canvas p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="demo-heading" className="text-base font-semibold text-navy">Scenario injection</h2>
        <DemoBadge>Demo only</DemoBadge>
      </div>
      <p className="mt-1 text-sm text-muted">
        Adds synthetic payments from the India simulator to the stream, at the stream&apos;s current time. Not available on real data.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-2 min-[420px]:grid-cols-2 lg:grid-cols-3 xl:grid-cols-7">
        {SCENARIOS.map((s) => (
          <button key={s.kind} type="button" onClick={() => inject(s.kind)} disabled={busy !== null}
                  className="flex min-h-11 flex-col items-start rounded-md border border-line-strong bg-surface px-3 py-2 text-left hover:border-teal hover:bg-teal-soft disabled:cursor-not-allowed disabled:opacity-55">
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
                Report it and trace the money
              </Link>
            </>
          ) : "Watch the case queue for any case it raises."}
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
      <PageHeader title="Command centre"
                  description="Every payment is scored as it arrives. Linked alerts become cases, ranked by tier and money at risk."
                  actions={<ConnectionStatus connected={connected} warmingUp={Boolean(stats.warming_up)} updatedAt={updatedAt} />} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        <Stat icon="activity" label="Payments scored" value={kpi(stats.processed, fmtInt)} hint="since the stream started" />
        <Stat icon="activity" label="Throughput" value={kpi(stats.tps, (n) => `${fmtInt(n)}/s`)} hint="payments per second" />
        <Stat icon="clock" label="p95 latency" value={kpi(stats.p95_latency_ms, (n) => `${n.toFixed(2)} ms`)} hint="per payment scored" />
        <Stat icon="critical" label="Alerts" value={kpi(stats.alerts, fmtInt)} hint="payments at or above alert score" />
        <div className="col-span-2 sm:col-span-1">
          <Stat icon="shield" label="Open cases" value={hasStats && stats.open_cases != null ? fmtInt(stats.open_cases) : cases ? fmtInt(cases.length) : "—"}
                hint="awaiting an officer's review" />
        </div>
      </div>

      {error && <ErrorNote title="Could not reach the Ripple API" error={error} onRetry={load} />}

      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Case queue" className="xl:col-span-2"
              description={cases ? <TierCounts cases={cases} /> : undefined}
              action={
                <div className="w-full sm:w-auto">
                  <label htmlFor="budget" className="flex items-center justify-between gap-3 text-sm font-semibold text-ink">
                    Alert budget
                    <output htmlFor="budget" className="min-w-12 rounded bg-sunken px-2 py-0.5 text-right tabular-nums">{budget}</output>
                  </label>
                  <input id="budget" type="range" min={5} max={100} step={5} value={budget} className="mt-1 w-full sm:w-56"
                         onChange={(e) => setBudget(Number(e.target.value))} aria-describedby="budget-hint" />
                  <p id="budget-hint" className="text-xs text-subtle">Top {budget} open cases shown</p>
                </div>
              }>
          {cases === null && !error ? (
            <p className="flex items-center gap-2 text-sm text-muted" role="status"><Spinner /> Loading cases…</p>
          ) : cases === null ? (
            <EmptyState icon="wifiOff" title="Case queue unavailable">Cases will load once the Ripple API is reachable again.</EmptyState>
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
