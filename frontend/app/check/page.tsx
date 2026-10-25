"use client";

import { useState, type FormEvent } from "react";

import { Button, Card, DemoBadge, ErrorNote, Field, Icon, inputClass, PageHeader, Spinner } from "@/components/ui";
import { api, money, prob, type CheckResult } from "@/lib/api";
import { reasonLabel } from "@/lib/labels";

const RAILS = ["UPI", "IMPS", "NEFT", "RTGS"];

const DECISION = {
  allow: { label: "Allow", cls: "bg-recover-soft text-recover ring-recover" },
  cooling_off: { label: "Cooling-off hold", cls: "bg-review-soft text-review ring-review-line" },
  hold_and_call: { label: "Hold and call", cls: "bg-critical text-white ring-critical" },
} as const;

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function CheckPage() {
  const [form, setForm] = useState({ src: "", dst: "", amount: "", rail: "IMPS" });
  const [result, setResult] = useState<CheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const check = async (f = form) => {
    setBusy("check");
    setError(null);
    try {
      setResult(await api.check({ src_account: f.src.trim(), dst_account: f.dst.trim(),
                                  amount: Number(f.amount.replace(/[,\s₹]/g, "")), rail: f.rail }));
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const coachedExample = async () => {
    setBusy("example");
    setError(null);
    setResult(null);
    try {
      const injected = await api.inject("fd_broken");
      const next = { src: injected.customer_account ?? "", dst: "SAFE-ACCOUNT-1", amount: "750000", rail: "RTGS" };
      setForm(next);
      await wait(2500); // the broken deposit has to reach the engine before the transfer is checked
      await check(next);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  const ordinaryExample = () => {
    const next = { src: form.src || "AC0038", dst: "SHOP001", amount: "450", rail: "UPI" };
    setForm(next);
    check(next);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    check();
  };

  const d = result ? DECISION[result.decision] : null;

  return (
    <div className="space-y-6">
      <PageHeader title="Check a payment"
                  description="The bank asks Ripple before a payment leaves. Ripple answers in about a millisecond: allow it, pause it for the customer to confirm, or hold it and call them." />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Payment about to go" className="lg:col-span-2">
          <form onSubmit={submit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="From account">
                {(a) => <input {...a} value={form.src} onChange={(e) => setForm({ ...form, src: e.target.value })} placeholder="AC0038" className={`${inputClass} font-mono`} required />}
              </Field>
              <Field label="To account">
                {(a) => <input {...a} value={form.dst} onChange={(e) => setForm({ ...form, dst: e.target.value })} placeholder="SAFE-ACCOUNT-1" className={`${inputClass} font-mono`} required />}
              </Field>
              <Field label="Amount (₹)">
                {(a) => <input {...a} inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} placeholder="7,50,000" className={`${inputClass} tabular-nums`} required />}
              </Field>
              <Field label="Rail">
                {(a) => (
                  <select {...a} value={form.rail} onChange={(e) => setForm({ ...form, rail: e.target.value })} className={inputClass}>
                    {RAILS.map((r) => <option key={r}>{r}</option>)}
                  </select>
                )}
              </Field>
            </div>
            <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
              <Button type="submit" variant="primary" disabled={busy !== null}>
                {busy === "check" ? <Spinner /> : <Icon name="shield" className="h-4 w-4" />} Check payment
              </Button>
              <p className="text-xs text-subtle">A check records nothing. The payment is scored for real only if it goes.</p>
            </div>
          </form>
        </Card>

        <section className="no-print rounded-card border-2 border-dashed border-line-strong bg-canvas p-4 sm:p-5" aria-labelledby="examples">
          <div className="flex items-center gap-2">
            <h2 id="examples" className="text-base font-semibold text-navy">Try it</h2>
            <DemoBadge>Demo only</DemoBadge>
          </div>
          <div className="mt-3 space-y-2">
            <button type="button" onClick={coachedExample} disabled={busy !== null}
                    className="flex w-full flex-col items-start rounded-md border border-line-strong bg-surface px-3 py-2 text-left hover:border-teal hover:bg-teal-soft disabled:opacity-55">
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">{busy === "example" && <Spinner className="h-3.5 w-3.5" />}A coached transfer</span>
              <span className="text-xs text-muted">A pensioner breaks an ₹8 lakh FD, then is told to send ₹7.5 lakh to a &quot;safe account&quot;.</span>
            </button>
            <button type="button" onClick={ordinaryExample} disabled={busy !== null}
                    className="flex w-full flex-col items-start rounded-md border border-line-strong bg-surface px-3 py-2 text-left hover:border-teal hover:bg-teal-soft disabled:opacity-55">
              <span className="text-sm font-semibold text-ink">An ordinary payment</span>
              <span className="text-xs text-muted">₹450 to a shop over UPI.</span>
            </button>
          </div>
        </section>
      </div>

      {error && <ErrorNote title="Check failed" error={error} onRetry={() => check()} />}

      {result && d && (
        <Card title="Decision" description={`Checked in ${result.checked_in_ms} ms · score ${prob(result.probability)}`}>
          <div className="flex flex-wrap items-center gap-3">
            <span className={`rounded-md px-2.5 py-1 text-sm font-semibold ring-1 ring-inset ${d.cls}`}>{d.label}</span>
            <p className="text-base font-semibold text-ink">{result.headline}</p>
          </div>
          {result.reasons.length > 0 && (
            <ul className="mt-4 space-y-2">
              {result.reasons.map((r) => (
                <li key={r.code + r.text} className="rounded-md border border-line p-3 text-sm">
                  <p className="font-semibold text-ink">{reasonLabel(r.code)}</p>
                  <p className="mt-0.5 text-muted">{r.text}</p>
                  {r.counterfactual && <p className="mt-1 text-xs text-subtle">{r.counterfactual}</p>}
                </li>
              ))}
            </ul>
          )}
          {result.customer_message && (
            <div className="mt-4 rounded-md bg-mist p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-subtle">Message to the customer</p>
              <p className="mt-1 text-sm text-ink">{result.customer_message}</p>
            </div>
          )}
          <p className="mt-4 text-xs text-subtle">
            {result.decision === "allow" ? `Payment of ${money(Number(form.amount.replace(/[,\s₹]/g, "")) || 0)} goes through.` :
              "A hold pauses the payment; it does not refuse it. The customer keeps control of their money."}
          </p>
        </Card>
      )}
    </div>
  );
}
