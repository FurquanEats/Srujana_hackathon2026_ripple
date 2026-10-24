"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { FreezePlan } from "@/components/FreezePlan";
import { MoneyGraph } from "@/components/MoneyGraph";
import { Card, ErrorNote, LayerTag, RiskDot, TierBadge } from "@/components/ui";
import { api, money, pct, time, type CaseDetail, type InterdictionPlan } from "@/lib/api";

export function Workbench() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [plan, setPlan] = useState<InterdictionPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.case(id), api.interdiction(id)])
      .then(([d, p]) => { setDetail(d); setPlan(p); })
      .catch((e) => setError(e.message));
  }, [id]);

  const edges = useMemo(() => (detail ? [...detail.edges].sort((a, b) => a.ts.localeCompare(b.ts)) : []), [detail]);
  const accounts = useMemo(() => {
    if (!detail) return [];
    const held = new Map(plan?.holdings.map((h) => [h.account_id, h.tainted]) ?? []);
    return detail.nodes.map((n) => ({ id: n.id, role: n.role === "other" ? "victim" : n.role, risk: n.risk, holding: held.get(n.id) }));
  }, [detail, plan]);

  if (error) return <ErrorNote error={error} />;
  if (!detail || !plan) return <p className="text-slate-400">Loading case {id}…</p>;

  const currency = detail.timeline[0]?.currency ?? "INR";
  const at = step === null ? undefined : edges[step]?.ts;

  const decide = async (v: "confirmed" | "dismissed") => {
    try {
      const r = await api.feedback(id, v);
      setVerdict(`${v === "confirmed" ? "Confirmed" : "Dismissed"}. Detector weight ${r.weights_before.detector.toFixed(2)} → ${r.weights_after.detector.toFixed(2)}; ${r.requeued} other cases re-ranked.`);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/" className="text-xs text-slate-500 hover:text-slate-300">← Case queue</Link>
          <h1 className="mt-1 flex items-center gap-3 text-2xl font-semibold tracking-tight">
            <span className="font-mono">{detail.case_id}</span> <TierBadge tier={detail.tier} />
          </h1>
          <p className="text-sm text-slate-400">
            Probability {detail.probability.toFixed(2)} · {detail.accounts} accounts · {detail.transactions} alerts ·
            opened {time(detail.opened_at)} · money at risk {money(detail.amount_at_risk, currency)}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => decide("confirmed")} className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold hover:bg-red-500">Confirm fraud</button>
          <button onClick={() => decide("dismissed")} className="rounded-md border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Dismiss</button>
        </div>
      </div>
      {verdict && <p className="rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm">{verdict}</p>}

      <FreezePlan plan={plan} currency={currency} />

      <Card title="Follow the money"
            action={edges.length > 1 && (
              <label className="flex items-center gap-2 text-xs text-slate-400">
                Replay <input type="range" min={0} max={edges.length - 1} value={step ?? edges.length - 1}
                              onChange={(e) => setStep(Number(e.target.value))} aria-label="Replay payments in time order" />
                <span className="w-28 text-slate-300">{time(at ?? edges[edges.length - 1].ts)}</span>
              </label>
            )}>
        <MoneyGraph edges={edges} accounts={accounts} frozen={plan.freeze.map((f) => f.account_id)} upTo={at} currency={currency} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Why Ripple flagged it">
          <ul className="space-y-3">
            {detail.reasons.map((r) => (
              <li key={r.code} className="text-sm">
                <div className="flex items-center gap-2"><LayerTag layer={r.layer} /><span className="text-xs text-slate-500">{r.code.replace(/_/g, " ")} · strength {pct(r.strength)}</span></div>
                <p className="mt-1 text-slate-200">{r.text}</p>
                {r.counterfactual && <p className="mt-0.5 text-xs text-slate-500">{r.counterfactual}</p>}
              </li>
            ))}
          </ul>
          {detail.shap.length > 0 && (
            <div className="mt-4 space-y-1">
              <h3 className="text-xs uppercase text-slate-500">Model contributions</h3>
              {detail.shap.map((s) => (
                <div key={s.feature} className="flex items-center gap-2 text-xs">
                  <span className="w-40 truncate text-slate-400">{s.feature}</span>
                  <span className="h-2 rounded" style={{ width: `${Math.min(100, Math.abs(s.contribution) * 40)}px`, background: s.contribution > 0 ? "#f87171" : "#34d399" }} />
                  <span className="tabular-nums text-slate-500">{s.contribution > 0 ? "+" : ""}{s.contribution.toFixed(2)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Timeline">
          <ol className="max-h-96 space-y-1 overflow-y-auto pr-1 text-xs">
            {detail.timeline.map((t) => (
              <li key={t.txn_id} className={`flex items-center gap-2 rounded px-2 py-1 ${t.is_alert ? "bg-red-500/10" : ""}`}>
                <RiskDot p={t.probability} />
                <span className="w-28 shrink-0 text-slate-500">{time(t.ts)}</span>
                <span className="truncate font-mono">{t.src_account} → {t.dst_account}</span>
                <span className="ml-auto tabular-nums">{money(t.amount, t.currency)}</span>
                <span className="w-12 text-right text-slate-500">{t.rail}</span>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </div>
  );
}
