"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Card, ErrorNote, RiskDot, Stat, TierBadge } from "@/components/ui";
import { api, money, time, type CaseSummary, type InjectResult } from "@/lib/api";
import { useStream } from "@/lib/useStream";

const SCENARIOS: [string, string][] = [
  ["digital_arrest", "Digital arrest"],
  ["mule_ring", "Mule ring"],
  ["scam_fanout", "Scam fan-out"],
  ["sim_swap_takeover", "SIM-swap takeover"],
  ["cash_structuring", "Cash structuring"],
  ["diwali_spike", "Diwali shopping (legit)"],
];

export default function CommandCentre() {
  const { feed, stats, lastCase, connected } = useStream();
  const [budget, setBudget] = useState(20);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [injected, setInjected] = useState<InjectResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    api.cases(budget).then((c) => { setCases(c); setError(null); }).catch((e) => setError(e.message));
  }, [budget]);

  useEffect(load, [load, lastCase]);

  const inject = async (kind: string) => {
    setBusy(kind);
    try {
      setInjected(await api.inject(kind));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Command centre</h1>
          <p className="text-sm text-slate-400">Every payment scored as it arrives; linked alerts become cases ranked by tier and money at risk.</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs ${connected ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>
          {connected ? "Live" : "Disconnected"}{stats.warming_up ? " · warming up" : ""}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Payments scored" value={(stats.processed ?? 0).toLocaleString("en-IN")} />
        <Stat label="Throughput" value={`${Math.round(stats.tps ?? 0).toLocaleString("en-IN")}/s`} />
        <Stat label="p95 latency" value={`${(stats.p95_latency_ms ?? 0).toFixed(2)} ms`} />
        <Stat label="Alerts" value={(stats.alerts ?? 0).toLocaleString("en-IN")} />
        <Stat label="Open cases" value={(stats.open_cases ?? cases.length).toLocaleString("en-IN")} />
      </div>

      <Card title="Inject a scenario" action={<span className="text-xs text-slate-500">from the India simulator, at the stream&apos;s current time</span>}>
        <div className="flex flex-wrap gap-2">
          {SCENARIOS.map(([kind, label]) => (
            <button key={kind} onClick={() => inject(kind)} disabled={busy !== null}
                    className="rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm hover:bg-slate-800 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400">
              {busy === kind ? "Injecting…" : label}
            </button>
          ))}
        </div>
        {injected && (
          <p className="mt-3 text-sm text-slate-300">
            Injected {injected.txn_ids.length} payments ({injected.kind.replace(/_/g, " ")}) at {time(injected.at)}.
            {injected.victim_account && (
              <> The victim is <span className="font-mono">{injected.victim_account}</span>.{" "}
                <Link className="text-sky-300 underline" href={`/trace?account=${injected.victim_account}&from=${encodeURIComponent(injected.victim_paid_at ?? injected.at)}`}>
                  Report it and trace the money
                </Link>
              </>
            )}
          </p>
        )}
      </Card>

      {error && <ErrorNote error={`Could not reach the Ripple API: ${error}`} />}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Case queue" className="lg:col-span-3"
              action={
                <label className="flex items-center gap-2 text-xs text-slate-400">
                  Alert budget <input type="range" min={5} max={100} step={5} value={budget} onChange={(e) => setBudget(Number(e.target.value))} aria-label="Alert budget" />
                  <span className="w-8 tabular-nums text-slate-200">{budget}</span>
                </label>
              }>
          {cases.length === 0 ? (
            <p className="text-sm text-slate-400">No open cases yet. Inject a scenario to see one appear.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr><th className="py-2">Case</th><th>Tier</th><th className="text-right">Probability</th><th className="text-right">Money at risk</th><th className="text-right">Accounts</th><th className="pl-4">Why</th></tr>
                </thead>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.case_id} className="border-t border-slate-800 hover:bg-slate-800/40">
                      <td className="py-2"><Link className="font-mono text-sky-300 hover:underline" href={`/cases/${c.case_id}`}>{c.case_id}</Link></td>
                      <td><TierBadge tier={c.tier} /></td>
                      <td className="text-right tabular-nums">{c.probability.toFixed(2)}</td>
                      <td className="text-right tabular-nums">{money(c.amount_at_risk)}</td>
                      <td className="text-right tabular-nums">{c.accounts}</td>
                      <td className="pl-4 text-xs text-slate-400">{c.typologies.slice(0, 3).join(", ").replace(/_/g, " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Live payments" className="lg:col-span-2">
          <ul className="max-h-[28rem] space-y-1 overflow-y-auto pr-1 text-xs" aria-live="polite">
            {feed.map((t) => (
              <li key={t.txn_id} className={`flex items-center gap-2 rounded px-2 py-1 ${t.is_alert ? "bg-red-500/10" : ""}`}>
                <RiskDot p={t.probability} />
                <span className="w-24 shrink-0 truncate font-mono text-slate-400">{t.src_account}</span>
                <span className="text-slate-600">→</span>
                <span className="w-24 shrink-0 truncate font-mono text-slate-400">{t.dst_account}</span>
                <span className="ml-auto tabular-nums">{money(t.amount, t.currency)}</span>
                <span className="w-12 text-right text-slate-500">{t.rail}</span>
              </li>
            ))}
            {feed.length === 0 && <li className="text-slate-500">Waiting for the stream…</li>}
          </ul>
        </Card>
      </div>
    </div>
  );
}
