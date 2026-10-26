import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Attention, Explainer, type QuickAction, type Tone } from "@/components/workspace/attention";
import { FlowGraph } from "@/components/workspace/flow-graph";
import { HoldTimeline } from "@/components/workspace/hold-timeline";
import { PrintButton } from "@/components/workspace/print-button";
import { creditsFlow } from "@/lib/flows";
import { Held, Money, Notice, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { account, holds, now } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";
import { statusLabel } from "@/lib/holds";

import { holdAction, holdNoteAction } from "../../actions";

const DAY = 86_400_000;

function next(
  hold: NonNullable<Awaited<ReturnType<typeof holds>>[number]>,
  clock: string,
): { tone: Tone; title: string; why: string; actions: QuickAction[] } {
  const due = (name: string) => hold.deadlines.find((d) => d.name === name && d.state === "open")?.due;
  const daysTo = (iso?: string) =>
    iso ? Math.round((new Date(iso).getTime() - new Date(clock).getTime()) / DAY) : null;
  if (hold.compliance_breach)
    return {
      tone: "urgent",
      title: hold.compliance_breach,
      why: "Fix this first: it is a breach of the directions.",
      actions: [{ label: "File the STR", href: "#next", primary: true }],
    };
  if (hold.released_at)
    return {
      tone: "done",
      title: "Released",
      why: hold.release_reason ?? "The hold has ended.",
      actions: [],
    };
  if (hold.mule_confirmed_at && !hold.str_filed_at)
    return {
      tone: "urgent",
      title: `File the STR with FIU-IND within ${daysTo(hold.str_due ?? undefined)} days`,
      why: "A confirmed mule without a filed STR is a compliance breach once the 7 working days pass.",
      actions: [
        { label: "Record the STR as filed", href: "#next", primary: true },
        { label: "Print the STR draft", href: "#str" },
      ],
    };
  switch (hold.status) {
    case "awaiting_explanation": {
      const d = daysTo(due("Customer explanation"));
      return {
        tone: "info",
        title: `Waiting for the customer: ${d} days left to explain`,
        why: "Record the explanation when it arrives. You can report to the police only after an explanation or once the 20 days have run out.",
        actions: [
          { label: "Record the explanation", href: "#next", primary: true },
          { label: "Add a note", href: "#notes" },
        ],
      };
    }
    case "explanation_received": {
      const d = daysTo(due("Bank decision"));
      return {
        tone: "action",
        title: `Decide within ${d} days: release or report`,
        why: "Read the customer's explanation and documents, then release the hold or report the transactions to the police through NCRP.",
        actions: [
          { label: "Decide", href: "#next", primary: true },
          { label: "Add a note", href: "#notes" },
        ],
      };
    }
    case "reported_to_police":
      return {
        tone: "info",
        title: "Reported to the police: waiting for their instruction",
        why: "Without an instruction, the hold ends on the 31st day from the report. Record the police instruction when it arrives.",
        actions: [{ label: "Record the police instruction", href: "#next", primary: true }],
      };
    case "held_on_police_instruction":
      return {
        tone: "info",
        title: "Held on the police's instruction",
        why: "The hold stays until the police say otherwise, within the 60-day cap. Confirm the account as a mule if the bank is satisfied it is one.",
        actions: hold.mule_confirmed_at ? [] : [{ label: "Confirm as a mule", href: "#next", primary: true }],
      };
    default:
      return { tone: "info", title: hold.status, why: "", actions: [] };
  }
}

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
  const profile = await account(session, hold.account_number).catch(() => null);
  const flow = profile ? creditsFlow(profile, hold.credit_txns) : null;
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
      {(() => {
        const n = next(hold, clock);
        return (
          <Attention
            tone={n.tone}
            title={n.title}
            actions={[
              ...n.actions,
              { label: "Open the account", href: `/app/accounts/${hold.account_number}` },
            ]}
            facts={[
              {
                label: hold.whole_account ? "On hold (whole account)" : "On hold (flagged amount)",
                value: open ? (
                  <Held paise={hold.amount} />
                ) : (
                  <Money paise={hold.amount} className="text-faint" />
                ),
              },
              { label: "Placed", value: formatIst(hold.placed_at) },
              { label: "Next deadline", value: hold.next_deadline ? formatIst(hold.next_deadline) : "None" },
              { label: "Ends at the latest", value: formatIst(hold.expires_at) },
            ]}
          >
            {n.why}
          </Attention>
        );
      })()}
      {flow && flow.inflows.length > 0 && (
        <FlowGraph
          title="The held credits, and what left in the next two days"
          centre={{ label: hold.holder_name ?? hold.account_number, sub: hold.account_number }}
          inflows={flow.inflows}
          outflows={flow.outflows}
          events={flow.events}
        />
      )}

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
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="pixel text-lg">Customer notice</h2>
            <PrintButton label="Print notice" />
          </div>
          <pre className="bg-panel border-line max-h-80 overflow-y-auto border p-4 font-sans text-[12.5px] leading-relaxed whitespace-pre-wrap">
            {hold.customer_notice}
          </pre>
        </div>
      </section>

      {open && (
        <section id="next" aria-labelledby="next-title" className="mb-10 scroll-mt-6">
          <h2 id="next-title" className="pixel mb-4 text-lg">
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
        <section id="str" aria-labelledby="str-title" className="mb-10 scroll-mt-6">
          <h2 id="str-title" className="pixel mb-3 text-lg">
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
      <section id="notes" className="mb-10 scroll-mt-6">
        <h2 className="pixel mb-3 text-lg">Notes and calls</h2>
        {(hold.notes ?? []).length === 0 ? (
          <p className="text-faint mb-4 text-sm">No notes yet.</p>
        ) : (
          <ol className="mb-4 grid gap-2">
            {(hold.notes ?? []).map((note, i) => (
              <li key={i} className="border-line border-l-2 pl-3 text-sm">
                <span className="text-faint block text-xs">
                  {formatIst(note.at)} · {note.actor}
                </span>
                {note.note}
              </li>
            ))}
          </ol>
        )}
        {open && (
          <form action={holdNoteAction} className="flex flex-wrap gap-2">
            <input type="hidden" name="hold_id" value={hold.hold_id} />
            <input
              name="note"
              required
              maxLength={2000}
              className="field min-w-64 flex-1"
              placeholder="Called the customer; documents promised by Friday"
              aria-label="Note"
            />
            <button className="button button-ghost">Add note</button>
          </form>
        )}
      </section>
      <Explainer title="The rules behind these deadlines">
        <p>
          RBI&apos;s draft directions on money mule accounts (Annex III): the customer is told at once and has
          20 days to explain; the bank decides within 10 days of an explanation, or 30 days from the hold
          without one.
        </p>
        <p>
          A hold reported to the police ends on the 31st day from the report unless the police instruct
          otherwise, and no hold lasts more than 60 days.
        </p>
        <p>
          A confirmed mule needs an STR with FIU-IND within 7 working days (PML Rules, rule 8(3)). Every step
          here is in the audit log.
        </p>
      </Explainer>
    </>
  );
}
