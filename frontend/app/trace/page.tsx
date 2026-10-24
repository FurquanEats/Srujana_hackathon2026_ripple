"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { FreezePlan } from "@/components/FreezePlan";
import { MoneyGraph } from "@/components/MoneyGraph";
import { Card, ErrorNote } from "@/components/ui";
import { api, time, type InterdictionPlan } from "@/lib/api";

function toLocalInput(ts: string | null) {
  if (!ts) return "";
  return ts.slice(0, 16);
}

function ReportForm() {
  const params = useSearchParams();
  const [account, setAccount] = useState(params.get("account") ?? "");
  const [from, setFrom] = useState(toLocalInput(params.get("from")));
  const [amount, setAmount] = useState("");
  const [plan, setPlan] = useState<InterdictionPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setPlan(await api.trace(account.trim(), from ? `${from}:00` : undefined, amount ? Number(amount) : undefined));
    } catch (e) {
      setPlan(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    // A link from the command centre carries the victim: trace straight away, once.
    if (params.get("account")) Promise.resolve().then(run);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const accounts = useMemo(() => {
    if (!plan) return [];
    const held = new Map(plan.holdings.map((h) => [h.account_id, h.tainted]));
    const ids = new Set(plan.edges.flatMap((e) => [e.source, e.target]));
    return [...ids].map((id) => ({ id, role: plan.victims.includes(id) ? "victim" : undefined, holding: held.get(id) }));
  }, [plan]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Report a scam</h1>
        <p className="max-w-3xl text-sm text-slate-400">
          For the bank officer handling a 1930 helpline or cybercrime-portal complaint. Enter the victim&apos;s account and
          when they paid; Ripple follows the money through every hop it can see, shows where it sits now, and drafts a
          hold request for each account to freeze.
        </p>
      </div>

      <Card>
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <label className="text-sm sm:col-span-1">
            <span className="text-xs text-slate-400">Victim&apos;s account</span>
            <input required value={account} onChange={(e) => setAccount(e.target.value)} placeholder="AC0037"
                   className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 font-mono" />
          </label>
          <label className="text-sm">
            <span className="text-xs text-slate-400">Paid from (optional)</span>
            <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)}
                   className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2" />
          </label>
          <label className="text-sm">
            <span className="text-xs text-slate-400">Amount reported (optional)</span>
            <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="750000"
                   className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2" />
          </label>
          <div className="flex items-end">
            <button disabled={busy || !account} className="w-full rounded-md bg-sky-600 px-4 py-2 font-semibold hover:bg-sky-500 disabled:opacity-50">
              {busy ? "Tracing…" : "Trace the money"}
            </button>
          </div>
        </form>
      </Card>

      {error && <ErrorNote error={error} />}

      {plan && (
        <>
          <p className="text-sm text-slate-400">Traced {plan.edges.length} payments from {plan.victims.join(", ")}, as of {time(plan.as_of)}.</p>
          <FreezePlan plan={plan} />
          <Card title="Where the money went">
            <MoneyGraph edges={plan.edges} accounts={accounts} frozen={plan.freeze.map((f) => f.account_id)} height={460} />
          </Card>
        </>
      )}
    </div>
  );
}

export default function TracePage() {
  return (
    <Suspense fallback={<p className="text-slate-400">Loading…</p>}>
      <ReportForm />
    </Suspense>
  );
}
