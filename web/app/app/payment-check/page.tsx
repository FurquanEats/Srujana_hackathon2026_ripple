import type { Metadata } from "next";

import { CardLink } from "@/components/workspace/cards";
import { Notice, PageHeader } from "@/components/workspace/ui";
import { accountText } from "@/lib/accounts";
import { formatInr } from "@/lib/format";
import { checkPayment, GatewayFailure, LIVE, savedChecks } from "@/lib/gateway/source";
import type { PaymentCheckRequest, PaymentCheckResult } from "@/lib/gateway/types";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Payment check" };

const DECISION = {
  allow: { label: "Allow", tone: "border-[var(--line)]" },
  warn: { label: "Warn the customer", tone: "border-amber-500" },
  cooling_hold: { label: "Cooling hold and call", tone: "border-amber-500" },
  hold_and_call: { label: "Hold and call the customer", tone: "border-red-500" },
} as const;

const SOURCE = { dpip: "DPIP", this_bank: "This bank", sender: "Customer's own history" } as const;

function Result({ request, result }: { request: PaymentCheckRequest; result: PaymentCheckResult }) {
  const d = DECISION[result.decision];
  return (
    <section aria-labelledby="result" className={`mb-10 border-l-4 ${d.tone} bg-panel p-5`}>
      <p className="text-faint text-xs">
        {formatInr(request.amount)} from {request.sender_account} to {accountText(request.payee)}
      </p>
      <h2 id="result" className="pixel mt-2 text-2xl">
        {d.label}
      </h2>
      <p className="mt-2 max-w-2xl text-[15px]">{result.headline}</p>
      <p className="text-faint mt-2 text-xs">
        DPIP answered &quot;{result.dpip_level.replace("_", " ")}&quot; in {result.dpip_ms} ms, by keyed
        hashes of the payee&apos;s identifiers only.
      </p>
      {result.reasons.length > 0 && (
        <ul className="mt-4 grid gap-2">
          {result.reasons.map((r) => (
            <li key={r.text} className="grid gap-1 text-sm sm:grid-cols-[170px_1fr]">
              <span className="text-faint">{SOURCE[r.source]}</span>
              <span>{r.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type Search = Promise<{
  example?: string;
  sender?: string;
  ifsc?: string;
  account?: string;
  vpa?: string;
  amount?: string;
}>;

export default async function PaymentCheckPage({ searchParams }: { searchParams: Search }) {
  const session = await requireRole("nodal_officer", "frm_analyst");
  const q = await searchParams;
  const examples = savedChecks(session);
  let shown: { request: PaymentCheckRequest; result: PaymentCheckResult } | null = null;
  let error: string | null = null;
  if (q.example !== undefined) {
    const found = examples[Number(q.example)];
    if (found) shown = found;
  } else if (q.sender && q.amount) {
    const request: PaymentCheckRequest = {
      sender_account: q.sender.trim(),
      payee: {
        ifsc: q.ifsc?.trim().toUpperCase() || null,
        account_number: q.account?.trim() || null,
        vpa: q.vpa?.trim() || null,
      },
      amount: Math.round(Number(q.amount) * 100),
    };
    try {
      shown = { request, result: await checkPayment(session, request) };
    } catch (e) {
      if (e instanceof GatewayFailure) error = e.message;
      else throw e;
    }
  }
  return (
    <>
      <PageHeader
        title="Payment check"
        lead="Before a customer's payment leaves, Ripple asks DPIP about the payee (the suspect registry built from CFCFRMS trails, and signals other banks published) and weighs the customer's own history, such as a lump sum that just arrived going to a payee they have never paid. It answers allow, warn, cooling hold, or hold and call."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {shown && <Result request={shown.request} result={shown.result} />}

      {examples.length > 0 && (
        <section className="mb-10">
          <h2 className="pixel mb-4 text-lg">Payments checked on the saved run</h2>
          <div className="grid gap-2 md:grid-cols-2">
            {examples.map((e, i) => (
              <CardLink key={e.label} href={`/app/payment-check?example=${i}`} title={e.label}>
                {DECISION[e.result.decision].label} · DPIP {e.result.dpip_level.replace("_", " ")} ·{" "}
                {e.result.dpip_ms} ms
              </CardLink>
            ))}
          </div>
        </section>
      )}

      <section className="border-line border p-5">
        <h2 className="pixel mb-1 text-lg">Check a payment</h2>
        <p className="text-muted mb-5 text-sm">
          {LIVE
            ? "Enter the paying customer's account at this bank and the payee."
            : "This copy runs on saved data, so it shows only the payments above. With the live network every field works."}
        </p>
        <form method="get" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label htmlFor="sender" className="label">
              Paying customer&apos;s account
            </label>
            <input
              id="sender"
              name="sender"
              required
              pattern="[0-9A-Z]{6,20}"
              className="field font-mono"
              defaultValue={q.sender}
            />
          </div>
          <div>
            <label htmlFor="amount" className="label">
              Amount (rupees)
            </label>
            <input
              id="amount"
              name="amount"
              type="number"
              min="1"
              step="1"
              required
              className="field"
              defaultValue={q.amount}
            />
          </div>
          <div>
            <label htmlFor="ifsc" className="label">
              Payee IFSC
            </label>
            <input id="ifsc" name="ifsc" className="field font-mono" defaultValue={q.ifsc} />
          </div>
          <div>
            <label htmlFor="account" className="label">
              Payee account number
            </label>
            <input id="account" name="account" className="field font-mono" defaultValue={q.account} />
          </div>
          <div>
            <label htmlFor="vpa" className="label">
              or payee UPI ID
            </label>
            <input id="vpa" name="vpa" className="field font-mono" defaultValue={q.vpa} />
          </div>
          <div className="flex items-end">
            <button className="button button-solid" disabled={!LIVE}>
              Check the payment
            </button>
          </div>
        </form>
        <p className="text-faint mt-4 text-xs">
          DoT&apos;s Financial Fraud Risk Indicator (FRI) scores mobile numbers. The simulated accounts carry
          no mobile numbers, so this check does not ask FRI.
        </p>
      </section>
    </>
  );
}
