import type { Metadata } from "next";

import { Explainer } from "@/components/workspace/attention";
import { Notice, PageHeader } from "@/components/workspace/ui";
import { LIVE } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";

import { fileComplaintAction } from "../../actions";

export const metadata: Metadata = { title: "File a complaint" };

export default async function NewComplaintPage({ searchParams }: { searchParams: Outcome }) {
  await requireRole("police_officer");
  const { error } = await searchParams;
  return (
    <>
      <PageHeader
        title="File a complaint"
        back={{ href: "/app/cases", label: "Cases" }}
        lead="Enter the victim's payment as the bank statement shows it. CFCFRMS sends a notice to the bank that received it, and every bank on the way answers through Ripple."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {!LIVE && (
        <Notice kind="error">
          This copy runs on saved data, so a new complaint cannot be traced here. Run the network and set
          RIPPLE_GATEWAY=live to file one.
        </Notice>
      )}
      <form action={fileComplaintAction} className="border-line grid gap-4 border p-5 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="victim">
            Victim&apos;s name
          </label>
          <input id="victim" name="victim" required minLength={2} maxLength={120} className="field" />
        </div>
        <div>
          <label className="label" htmlFor="channel">
            Reported through
          </label>
          <select id="channel" name="channel" className="field" defaultValue="3">
            <option value="3">The 1930 helpline</option>
            <option value="2">cybercrime.gov.in</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="rail">
            Rail
          </label>
          <select id="rail" name="rail" className="field" defaultValue="imps">
            <option value="upi">UPI</option>
            <option value="imps">IMPS</option>
            <option value="neft">NEFT</option>
            <option value="rtgs">RTGS</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="reference">
            UTR or RRN
          </label>
          <input
            id="reference"
            name="reference"
            required
            minLength={6}
            maxLength={32}
            className="field font-mono"
          />
        </div>
        <div>
          <label className="label" htmlFor="amount">
            Amount (rupees)
          </label>
          <input id="amount" name="amount" type="number" min="1" step="1" required className="field" />
        </div>
        <div>
          <label className="label" htmlFor="at">
            When the victim paid
          </label>
          <input id="at" name="at" type="datetime-local" required className="field" />
        </div>
        <div>
          <label className="label" htmlFor="ifsc">
            Beneficiary IFSC
          </label>
          <input
            id="ifsc"
            name="ifsc"
            required
            pattern="[A-Za-z]{4}0[A-Za-z0-9]{6}"
            className="field font-mono"
          />
        </div>
        <div>
          <label className="label" htmlFor="account">
            Beneficiary account number
          </label>
          <input id="account" name="account" required pattern="[0-9]{6,20}" className="field font-mono" />
        </div>
        <button className="button button-solid justify-self-start" disabled={!LIVE}>
          File and trace
        </button>
      </form>
      <Explainer>
        <p>
          The acknowledgement number starts with 3 for a 1930 call and 2 for a complaint on cybercrime.gov.in
          (H1).
        </p>
        <p>
          The first notice goes to the bank that received the payment. Its answer names the next hops, and
          CFCFRMS follows them until the trail is complete.
        </p>
      </Explainer>
    </>
  );
}
