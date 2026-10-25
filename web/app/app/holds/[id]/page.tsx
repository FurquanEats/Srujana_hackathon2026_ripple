import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { HoldTimeline } from "@/components/workspace/hold-timeline";
import { Held, Money, Notice, PageHeader, Stat } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { holds, now } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";
import { statusLabel } from "@/lib/holds";

import { holdAction } from "../../actions";

export const metadata: Metadata = { title: "Debit hold" };

function Step({
  id,
  action,
  title,
  lead,
  children,
  submit,
}: {
  id: string;
  action: string;
  title: string;
  lead: string;
  children: React.ReactNode;
  submit: string;
}) {
  return (
    <form action={holdAction} className="border-line grid gap-3 border p-5">
      <input type="hidden" name="hold_id" value={id} />
      <input type="hidden" name="action" value={action} />
      <h3 className="pixel text-base">{title}</h3>
      <p className="text-muted text-[13px]">{lead}</p>
      {children}
      <button className="button button-solid justify-self-start">{submit}</button>
    </form>
  );
}

export default async function HoldPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Outcome;
}) {
  const session = await requireRole("frm_analyst");
  const { id } = await params;
  const { error, done } = await searchParams;
  const hold = (await holds(session)).find((h) => h.hold_id === id);
  if (!hold) notFound();
  const clock = await now(session);
  const open = !hold.released_at;
  const str = hold.str_draft as {
    grounds_of_suspicion?: string[];
    linked_ncrp_acknowledgements?: string[];
  } | null;
  return (
    <>
      <PageHeader
        title={hold.holder_name ?? hold.account_number}
        back={{ href: "/app/holds", label: "Debit holds" }}
        lead={statusLabel(hold)}
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      {hold.compliance_breach && <Notice kind="error">{hold.compliance_breach}</Notice>}
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <Stat label={hold.whole_account ? "Held (whole account)" : "Held (flagged amount only)"}>
          {open ? <Held paise={hold.amount} /> : <Money paise={hold.amount} className="text-faint" />}
        </Stat>
        <Stat label="Account">
          <span className="font-mono text-base">{hold.account_number}</span>
        </Stat>
        <Stat label="Placed">
          <span className="text-base">{formatIst(hold.placed_at)}</span>
        </Stat>
      </div>

      <section aria-labelledby="deadlines" className="mb-10">
        <h2 id="deadlines" className="pixel mb-2 text-lg">
          Deadlines
        </h2>
        <HoldTimeline hold={hold} now={clock} />
      </section>

      <section className="mb-10 grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="pixel mb-3 text-lg">Why</h2>
          <ul className="text-muted grid gap-2 text-sm leading-relaxed">
            {hold.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {hold.account_level_reason && (
            <p className="text-muted mt-3 text-sm">Whole account: {hold.account_level_reason}</p>
          )}
          {hold.explanation && (
            <>
              <h3 className="text-fg mt-6 text-sm">
                Customer&apos;s explanation, {formatIst(hold.explanation_at ?? hold.placed_at)}
              </h3>
              <p className="text-muted mt-1 text-sm">{hold.explanation}</p>
            </>
          )}
          {hold.decision_reason && (
            <>
              <h3 className="text-fg mt-6 text-sm">Bank&apos;s decision: {hold.decision}</h3>
              <p className="text-muted mt-1 text-sm">{hold.decision_reason}</p>
            </>
          )}
          {hold.release_reason && (
            <p className="text-muted mt-4 text-sm">
              Released {formatIst(hold.released_at ?? "")}: {hold.release_reason}
            </p>
          )}
        </div>
        <div>
          <h2 className="pixel mb-3 text-lg">Customer notice</h2>
          <pre className="bg-panel border-line max-h-80 overflow-y-auto border p-4 font-sans text-[12.5px] leading-relaxed whitespace-pre-wrap">
            {hold.customer_notice}
          </pre>
        </div>
      </section>

      {open && (
        <section aria-labelledby="next" className="mb-10">
          <h2 id="next" className="pixel mb-4 text-lg">
            Next step
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {hold.status === "awaiting_explanation" && (
              <Step
                id={hold.hold_id}
                action="explanation"
                title="Record the customer's explanation"
                lead="Summarise what the customer sent and the documents attached. The bank then has 10 days to decide."
                submit="Record explanation"
              >
                <textarea
                  name="summary"
                  required
                  maxLength={2000}
                  rows={3}
                  className="field"
                  aria-label="Summary of the explanation"
                />
              </Step>
            )}
            {(hold.status === "awaiting_explanation" || hold.status === "explanation_received") && (
              <Step
                id={hold.hold_id}
                action="decision"
                title="Decide"
                lead="Release the hold, or report the transactions to the police through NCRP. Reporting is allowed only after an explanation or once the 20 days have run out."
                submit="Record decision"
              >
                <select name="decision" className="field" aria-label="Decision" defaultValue="release">
                  <option value="release">Release the hold</option>
                  <option value="report">Report to the police</option>
                </select>
                <textarea
                  name="reason"
                  required
                  maxLength={2000}
                  rows={3}
                  className="field"
                  aria-label="Reason for the decision"
                  placeholder="Reason"
                />
              </Step>
            )}
            {hold.status === "reported_to_police" && (
              <Step
                id={hold.hold_id}
                action="instruction"
                title="Police instruction"
                lead="Record what the police asked for. Without an instruction, the hold ends on the 31st day from the report."
                submit="Record instruction"
              >
                <select name="instruction" className="field" aria-label="Instruction" defaultValue="continue">
                  <option value="continue">Continue the hold</option>
                  <option value="release">Release the hold</option>
                </select>
                <input
                  name="authority"
                  required
                  minLength={3}
                  maxLength={200}
                  className="field"
                  aria-label="Police authority"
                  placeholder="Police station or officer"
                />
              </Step>
            )}
            {!hold.mule_confirmed_at && (
              <Step
                id={hold.hold_id}
                action="confirm"
                title="Confirm as a mule"
                lead="Once the bank is satisfied the account is a mule, Ripple drafts the STR, due to FIU-IND within 7 working days."
                submit="Confirm and draft the STR"
              >
                <textarea
                  name="grounds"
                  required
                  maxLength={2000}
                  rows={3}
                  className="field"
                  aria-label="Grounds"
                  placeholder="Grounds"
                />
              </Step>
            )}
            {hold.mule_confirmed_at && !hold.str_filed_at && (
              <Step
                id={hold.hold_id}
                action="str"
                title="Record the STR as filed"
                lead={`Due by ${formatIst(hold.str_due ?? "")}. Enter FIU-IND's reference once filed through FINnet.`}
                submit="Record STR filed"
              >
                <input
                  name="reference"
                  required
                  minLength={3}
                  maxLength={64}
                  className="field"
                  aria-label="FIU-IND reference"
                  placeholder="FIU-IND reference"
                />
              </Step>
            )}
          </div>
        </section>
      )}

      {str && (
        <section aria-labelledby="str">
          <h2 id="str" className="pixel mb-3 text-lg">
            STR draft {hold.str_filed_at ? `(filed, reference ${hold.str_reference})` : ""}
          </h2>
          <div className="bg-panel border-line border p-4 text-sm">
            <p className="text-faint text-xs">Grounds of suspicion</p>
            <ol className="text-muted mt-2 list-decimal space-y-1 pl-5">
              {(str.grounds_of_suspicion ?? []).map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ol>
            {str.linked_ncrp_acknowledgements && str.linked_ncrp_acknowledgements.length > 0 && (
              <p className="text-faint mt-3 text-xs">
                Linked NCRP acknowledgements: {str.linked_ncrp_acknowledgements.join(", ")}
              </p>
            )}
          </div>
        </section>
      )}
    </>
  );
}
