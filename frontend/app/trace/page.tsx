"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { FreezeList, RecoveryChart, RecoveryMetrics } from "@/components/FreezePlan";
import { LearnFromTrail } from "@/components/LearnPattern";
import { MoneyGraph } from "@/components/MoneyGraph";
import { Button, Card, EmptyState, ErrorNote, Field, Icon, inputClass, LoadingPanel, Notice, PageHeader, Spinner } from "@/components/ui";
import { api, money, time, type InterdictionPlan, type LearnRequest } from "@/lib/api";

type Errors = Partial<Record<"account" | "date" | "time" | "amount", string>>;

const ACCOUNT = /^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$/;

/** "2026-10-30T16:08:59" -> ["2026-10-30", "16:08:59"]. Timestamps stay in the stream's local time, as the API expects. */
function splitTs(ts: string | null): [string, string] {
  if (!ts || ts.length < 16) return ["", ""];
  return [ts.slice(0, 10), ts.slice(11, 19)];
}
const withSeconds = (c: string) => (c.length === 5 ? `${c}:00` : c);

const parseAmount = (s: string) => Number(s.replace(/[,\s₹]/g, ""));

function validate(account: string, date: string, clock: string, amount: string): Errors {
  const e: Errors = {};
  if (!account.trim()) e.account = "Enter the victim's account number.";
  else if (!ACCOUNT.test(account.trim())) e.account = "Use letters, digits, hyphens or underscores only, for example AC0037.";
  if (date && !clock) e.time = "Add the time of the payment, or clear the date.";
  if (clock && !date) e.date = "Add the date of the payment, or clear the time.";
  if (amount.trim()) {
    const n = parseAmount(amount);
    if (!Number.isFinite(n) || n <= 0) e.amount = "Enter the amount in rupees, for example 7,50,000.";
  }
  return e;
}

function GoldenHour() {
  return (
    <aside aria-labelledby="golden-hour" className="rounded-card border border-line bg-mist p-4 sm:p-5">
      <h2 id="golden-hour" className="flex items-center gap-2 text-base font-semibold text-navy">
        <Icon name="clock" className="h-4 w-4 text-teal-strong" /> Why the golden hour matters
      </h2>
      <p className="mt-2 text-sm text-ink">
        Stolen money usually passes through two or three mule accounts within minutes, and some of it reaches an ATM or a
        crypto off-ramp soon after. Once it leaves the bank as cash or crypto it is very hard to recover.
      </p>
      <p className="mt-2 text-sm text-ink">
        Tracing straight from the report shows where the money sits <em>now</em> and the fewest accounts to hold to recover
        the most of it.
      </p>
      <ul className="mt-3 space-y-1.5 text-sm text-muted">
        <li className="flex gap-2"><Icon name="check" className="mt-0.5 h-4 w-4 text-teal-strong" />For complaints from the 1930 helpline or the cybercrime portal.</li>
        <li className="flex gap-2"><Icon name="check" className="mt-0.5 h-4 w-4 text-teal-strong" />Ripple drafts hold requests; an officer reviews and sends them.</li>
        <li className="flex gap-2"><Icon name="check" className="mt-0.5 h-4 w-4 text-teal-strong" />Only payments inside this bank&apos;s view are traced.</li>
      </ul>
    </aside>
  );
}

function ReportForm() {
  const params = useSearchParams();
  const [initDate, initTime] = splitTs(params.get("from"));
  const [account, setAccount] = useState(params.get("account") ?? "");
  const [date, setDate] = useState(initDate);
  const [clock, setClock] = useState(initTime);
  const [amount, setAmount] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [plan, setPlan] = useState<InterdictionPlan | null>(null);
  const [traced, setTraced] = useState<LearnRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const run = async (acc = account, d = date, c = clock, amt = amount) => {
    setBusy(true);
    setError(null);
    try {
      const n = amt.trim() ? parseAmount(amt) : undefined;
      const from = d && c ? `${d}T${withSeconds(c)}` : undefined;
      setPlan(await api.trace(acc.trim(), from, n));
      setTraced({ account: acc.trim(), from_ts: from ?? null, amount: n ?? null });
      requestAnimationFrame(() => resultRef.current?.focus());
    } catch (e) {
      setPlan(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const found = validate(account, date, clock, amount);
    setErrors(found);
    const first = Object.keys(found)[0];
    if (first) {
      formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
      return;
    }
    run();
  };

  useEffect(() => {
    // A link from the command centre carries the victim: trace straight away, once.
    if (params.get("account")) Promise.resolve().then(() => run());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const accounts = useMemo(() => {
    if (!plan) return [];
    const held = new Map(plan.holdings.map((h) => [h.account_id, h.tainted]));
    const ids = new Set(plan.edges.flatMap((e) => [e.source, e.target]));
    return [...ids].map((id) => ({ id, role: plan.victims.includes(id) ? "victim" : undefined, holding: held.get(id) }));
  }, [plan]);

  const amountPreview = amount.trim() && !errors.amount && Number.isFinite(parseAmount(amount)) && parseAmount(amount) > 0
    ? money(parseAmount(amount)) : null;

  return (
    <div className="space-y-6">
      <PageHeader title="Report a scam"
                  description="For the officer handling a 1930 helpline or cybercrime-portal complaint. Enter the victim's account and when they paid; Ripple follows the money through every hop it can see." />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Victim's report" className="lg:col-span-2">
          <form ref={formRef} noValidate onSubmit={submit} aria-busy={busy} className="space-y-5">
            <Field label="Victim's account number" error={errors.account} hint="The account the money was paid from, for example AC0037.">
              {(a) => (
                <input {...a} name="account" value={account} autoComplete="off" spellCheck={false} required aria-required
                       onChange={(e) => { setAccount(e.target.value); if (errors.account) setErrors({ ...errors, account: undefined }); }}
                       placeholder="AC0037" className={`${inputClass} font-mono sm:max-w-xs`} />
              )}
            </Field>

            <fieldset>
              <legend className="flex items-baseline gap-2 text-sm font-semibold text-ink">
                Paid from <span className="text-xs font-normal text-subtle">Optional</span>
              </legend>
              <p className="mt-0.5 text-xs text-subtle">When the victim made the first payment. Leave blank to trace the whole visible window (72 hours).</p>
              <div className="mt-2 grid grid-cols-2 gap-3 sm:max-w-md">
                <Field label="Date" error={errors.date}>
                  {(a) => (
                    <input {...a} name="date" type="date" value={date} className={inputClass}
                           onChange={(e) => { setDate(e.target.value); setErrors({ ...errors, date: undefined, time: undefined }); }} />
                  )}
                </Field>
                <Field label="Time" error={errors.time}>
                  {(a) => (
                    <input {...a} name="time" type="time" step={1} value={clock} className={inputClass}
                           onChange={(e) => { setClock(e.target.value); setErrors({ ...errors, date: undefined, time: undefined }); }} />
                  )}
                </Field>
              </div>
              {(date || clock) && (
                <button type="button" onClick={() => { setDate(""); setClock(""); setErrors({ ...errors, date: undefined, time: undefined }); }}
                        className="mt-1 min-h-9 rounded px-1 text-sm font-semibold text-link hover:bg-mist">Clear date and time</button>
              )}
            </fieldset>

            <Field label="Amount reported" optional error={errors.amount}
                   hint={amountPreview ? <>Reads as <span className="font-semibold text-ink">{amountPreview}</span></> : "In rupees. Commas are fine: 7,50,000."}>
              {(a) => (
                <div className="relative sm:max-w-xs">
                  <span aria-hidden className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted">₹</span>
                  <input {...a} name="amount" inputMode="decimal" value={amount} placeholder="7,50,000" autoComplete="off"
                         onChange={(e) => { setAmount(e.target.value); if (errors.amount) setErrors({ ...errors, amount: undefined }); }}
                         className={`${inputClass} pl-7 tabular-nums`} />
                </div>
              )}
            </Field>

            <div className="flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center">
              <Button type="submit" variant="primary" size="lg" disabled={busy} className="w-full sm:w-auto">
                {busy ? <><Spinner /> Tracing the money…</> : <><Icon name="search" className="h-5 w-5" /> Trace the money</>}
              </Button>
              <p className="text-xs text-subtle">Tracing reads payments only. It does not place holds on accounts or contact anyone.</p>
            </div>
          </form>
        </Card>

        <GoldenHour />
      </div>

      {error && <ErrorNote title="Trace failed" error={error} onRetry={() => run()} />}

      {busy && !plan && <LoadingPanel label="Following the money hop by hop…" />}

      {plan && (
        <div ref={resultRef} tabIndex={-1} className="space-y-6 focus:outline-none" aria-labelledby="trace-result">
          <h2 id="trace-result" className="sr-only">Trace result</h2>
          {plan.edges.length === 0 ? (
            <EmptyState icon="search" title="No onward payments found">
              Ripple found no payments from {plan.victims.join(", ") || account} in its window. Check the account number and the time of payment.
            </EmptyState>
          ) : (
            <>
              <Notice tone="success" title="Trace complete">
                Traced {plan.edges.length} payment{plan.edges.length === 1 ? "" : "s"} from <span className="font-mono">{plan.victims.join(", ")}</span>, as of {time(plan.as_of)}.
              </Notice>
              <RecoveryMetrics plan={plan} />
              <Card title="Where the money went" description="Left to right by hop. Accounts with a teal ring are recommended for a hold.">
                <MoneyGraph edges={plan.edges} accounts={accounts} frozen={plan.freeze.map((f) => f.account_id)} height={460} />
              </Card>
              <FreezeList plan={plan} />
              <RecoveryChart plan={plan} />
              {traced && <LearnFromTrail key={`${traced.account}-${traced.from_ts}`} request={traced} what="this scam" />}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function TracePage() {
  return (
    <Suspense fallback={<LoadingPanel label="Loading…" />}>
      <ReportForm />
    </Suspense>
  );
}
