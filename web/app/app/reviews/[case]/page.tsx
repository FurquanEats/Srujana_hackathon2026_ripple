import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Attention, Explainer } from "@/components/workspace/attention";
import { PrintButton } from "@/components/workspace/print-button";
import { Money, Notice, PageHeader, Stat } from "@/components/workspace/ui";
import { formatInr, formatIst } from "@/lib/format";
import { filedGrievances, now, reviews } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";
import { ACTION, CHECKS, VERDICT } from "@/lib/review/labels";
import type { Quoted } from "@/lib/review/types";

import { fileGrievanceAction, verdictAction } from "../../actions";

const DAY = 86_400_000;

export const metadata: Metadata = { title: "Evidence pack" };

const FIELDS = [
  ["document_type", "Type"],
  ["issuer", "Issuer"],
  ["issuer_gstin", "Issuer GSTIN"],
  ["recipient", "Buyer or recipient"],
  ["number", "Number"],
  ["date", "Date"],
  ["taxable_value", "Taxable value"],
  ["total", "Total"],
  ["payment_reference", "Payment reference"],
] as const;

function Field({ name, q }: { name: string; q: Quoted }) {
  return (
    <tr>
      <td className="text-faint whitespace-nowrap">{name}</td>
      <td>{q.value ?? <span className="text-faint">Not on the document</span>}</td>
      <td className="text-muted text-xs">
        {q.quote ? (
          <>
            &ldquo;{q.quote}&rdquo;{q.page ? `, page ${q.page}` : ""}
          </>
        ) : q.value ? (
          <span className="text-red-500">No quote: unverified</span>
        ) : null}
      </td>
    </tr>
  );
}

export default async function ReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ case: string }>;
  searchParams: Outcome;
}) {
  const session = await requireRole("grievance_officer");
  const { case: id } = await params;
  const { error, done } = await searchParams;
  const pack = (await reviews()).find((p) => p.case_id === id);
  if (!pack) notFound();
  const kyc = pack.holder.kyc;
  const filed = (await filedGrievances()).get(pack.case_id);
  const clock = await now(session);
  const undecided = pack.credits.filter((c) => !pack.decisions[c.credit_id]).length;
  const explained = pack.verdicts
    .filter((v) => v.verdict === "explained")
    .reduce((s, v) => s + v.explained_amount, 0);
  const keep = pack.verdicts.reduce((s, v) => s + v.hold_after, 0);
  const declared = kyc.declared_annual_turnover ?? kyc.declared_annual_income;
  return (
    <>
      <PageHeader
        title={pack.holder.name}
        back={{ href: "/app/reviews", label: "Evidence packs" }}
        lead={`${pack.case_id}: ${pack.title}. Account ${pack.holder.account_number} (${pack.holder.ifsc}).`}
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      {!pack.read ? (
        <Attention tone="info" title="Waiting for Gemini to read every document" />
      ) : filed ? (
        <Attention
          tone="info"
          title={`Grievance filed ${formatIst(filed)}: the investigating officer decides by ${formatIst(new Date(new Date(filed).getTime() + 15 * DAY).toISOString())}`}
          facts={[
            { label: "Explained", value: <Money paise={explained} /> },
            { label: "Proposed to stay on hold", value: <Money paise={keep} /> },
            {
              label: "Days since filing",
              value: Math.max(0, Math.round((new Date(clock).getTime() - new Date(filed).getTime()) / DAY)),
            },
            { label: "If no decision", value: "Escalate to the district grievance officer" },
          ]}
        >
          The SOP gives the investigating officer 15 days to decide on a grievance; without a decision, it
          goes to the district grievance officer (H5).
        </Attention>
      ) : undecided > 0 ? (
        <Attention
          tone="action"
          title={`Confirm or overrule ${undecided} verdict${undecided === 1 ? "" : "s"}`}
          actions={[{ label: "Go to the verdicts", href: "#verdicts", primary: true }]}
        >
          Nothing is filed until you have decided every held credit (G4). The bank must file within 7 days of
          receiving the holder&apos;s explanation.
        </Attention>
      ) : (
        <Attention
          tone="action"
          title="Every verdict decided: file the grievance"
          facts={[
            { label: "Explained", value: <Money paise={explained} /> },
            { label: "Proposed to stay on hold", value: <Money paise={keep} /> },
          ]}
        >
          <form action={fileGrievanceAction} className="mt-3 flex flex-wrap gap-2">
            <input type="hidden" name="case" value={pack.case_id} />
            <button className="button button-solid">File the grievance with this evidence pack</button>
          </form>
        </Attention>
      )}
      <div className="no-print mb-6 flex justify-end">
        <PrintButton label="Print the evidence pack" />
      </div>
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <Stat label="Declared at account opening">
          <span className="text-base">
            {kyc.occupation ?? kyc.business_type}
            {declared ? `, ${formatInr(declared)} a year` : ""}
          </span>
        </Stat>
        <Stat label="GSTIN on KYC">
          <span className="font-mono text-base">{pack.holder.gstin ?? "None"}</span>
        </Stat>
        <Stat label="TDS the payer may deduct">
          <span className="text-base">{pack.tds_rate_percent ? `${pack.tds_rate_percent}%` : "None"}</span>
        </Stat>
      </div>
      {pack.explanation && (
        <section className="mb-8">
          <h2 className="pixel mb-2 text-lg">The holder&apos;s explanation</h2>
          <blockquote className="border-line text-muted border-l-2 pl-4 text-[15px]">
            {pack.explanation}
          </blockquote>
        </section>
      )}

      <section id="verdicts" className="mb-10 scroll-mt-6">
        <h2 className="pixel mb-4 text-lg">Held credits and verdicts</h2>
        {!pack.read && (
          <Notice kind="error">
            Gemini has not read every document in this pack yet (the free tier&apos;s daily quota ran out), so
            no verdict is shown. Nothing is guessed.
          </Notice>
        )}
        <div className="grid gap-4">
          {pack.credits.map((c) => {
            const v = pack.verdicts.find((x) => x.credit_id === c.credit_id);
            const decided = pack.decisions[c.credit_id];
            return (
              <article key={c.credit_id} className="border-line min-w-0 border p-5">
                <div className="flex flex-wrap items-baseline justify-between gap-3">
                  <p className="text-[15px]">
                    {c.credit_id}: <Money paise={c.amount} /> by {c.rail.toUpperCase()} {c.reference}
                  </p>
                  {v && (
                    <span className={`px-2 py-0.5 text-sm ${VERDICT[v.verdict].tone}`}>
                      {VERDICT[v.verdict].label}
                    </span>
                  )}
                </div>
                <p className="text-muted mt-1 text-sm">
                  From {c.remitter.name}
                  {c.remitter.account_number ? ` (${c.remitter.account_number})` : ""} on {formatIst(c.at)}.
                  Traced amount {formatInr(c.traced_amount)}.
                </p>
                {v && (
                  <>
                    <p className="mt-3 text-sm">
                      Proposed: <strong className="font-normal">{ACTION[v.proposed_action]}</strong>
                      {v.proposed_action !== "lift" ? `, keeping ${formatInr(v.hold_after)} on hold` : ""}.
                      {v.document ? ` Matched to ${v.document}.` : ""}
                    </p>
                    <ul className="mt-3 grid gap-1 text-sm">
                      {Object.entries(CHECKS).map(([key, label]) => {
                        const failed = v.failed_checks.includes(key);
                        return (
                          <li key={key} className={failed ? "text-red-500" : "text-muted"}>
                            <span aria-hidden className="mr-2 font-mono">
                              {failed ? "✕" : "✓"}
                            </span>
                            {label}
                          </li>
                        );
                      })}
                    </ul>
                    {v.reasons.length > 0 && (
                      <ul className="mt-3 grid gap-1 text-sm">
                        {v.reasons.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    )}
                    {decided ? (
                      <p className="mt-4 text-sm">
                        You {decided.d} this verdict on {formatIst(decided.at)}
                        {decided.n ? `: ${decided.n}` : "."}
                      </p>
                    ) : (
                      <form
                        action={verdictAction}
                        className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end"
                      >
                        <input type="hidden" name="case" value={pack.case_id} />
                        <input type="hidden" name="credit" value={c.credit_id} />
                        <div>
                          <label htmlFor={`n-${c.credit_id}`} className="label">
                            Note (needed to overrule)
                          </label>
                          <input id={`n-${c.credit_id}`} name="note" maxLength={1000} className="field" />
                        </div>
                        <button name="decision" value="confirmed" className="button button-solid">
                          Confirm verdict
                        </button>
                        <button name="decision" value="overruled" className="button button-ghost">
                          Overrule
                        </button>
                      </form>
                    )}
                  </>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section>
        <h2 className="pixel mb-4 text-lg">Documents, as Gemini read them</h2>
        <div className="grid gap-6">
          {pack.documents.map((d) => (
            <article key={d.file} className="border-line min-w-0 border p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <a href={d.url} target="_blank" rel="noreferrer" className="link text-[15px]">
                  {d.file} ↗
                </a>
                <span className="text-faint text-xs">
                  {d.form}, {d.quality}, {d.language === "hi" ? "Hindi" : "English"}
                </span>
              </div>
              {d.extraction ? (
                <div className="mt-3 overflow-x-auto">
                  {!d.extraction.readable && (
                    <p className="mb-2 text-sm text-red-500">Gemini marked this document unreadable.</p>
                  )}
                  <table className="table min-w-[560px]">
                    <thead>
                      <tr>
                        <th>Field</th>
                        <th>Value read</th>
                        <th>Words on the page</th>
                      </tr>
                    </thead>
                    <tbody>
                      {FIELDS.map(([key, name]) => (
                        <Field key={key} name={name} q={d.extraction![key]} />
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-faint mt-3 text-sm">Not read yet.</p>
              )}
            </article>
          ))}
        </div>
        <p className="text-faint mt-6 text-xs">
          Verdicts say only whether the documents agree with the bank&apos;s records, never that a document is
          genuine. Text inside a document cannot change a verdict: the model only fills the fields, and the
          rules decide.
        </p>
      </section>
      <Explainer>
        <p>
          Gemini only fills fixed fields, quoting the words on the page behind each one; a field with no quote
          is unverified and can never support an explained verdict (G2).
        </p>
        <p>
          Fixed rules decide each credit: amount, date, payer, GSTIN, reuse and fit with the declared business
          (G3). Text inside a document cannot change a verdict.
        </p>
        <p>
          The evidence pack goes to the investigating officer through the CFCFRMS grievance module (SOP
          10.1(a)). Verdicts say the documents agree with the bank&apos;s records, never that they are
          genuine.
        </p>
      </Explainer>
    </>
  );
}
