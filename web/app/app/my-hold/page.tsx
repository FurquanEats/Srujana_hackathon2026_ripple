import type { Metadata } from "next";

import { Attention } from "@/components/workspace/attention";
import { HoldTimeline } from "@/components/workspace/hold-timeline";
import { Empty, Held, Money, Notice, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { myHolds, now } from "@/lib/gateway/source";
import type { Hold } from "@/lib/gateway/types";
import { requireRole, type Outcome } from "@/lib/guard";
import { statusLabel } from "@/lib/holds";

import { callBackAction, myExplanationAction } from "../actions";

export const metadata: Metadata = { title: "My hold" };

export default async function MyHoldPage({ searchParams }: { searchParams: Outcome }) {
  const session = await requireRole("account_holder");
  const { error, done } = await searchParams;
  const [mine, clock] = await Promise.all([myHolds(session), now(session)]);
  return (
    <>
      <PageHeader
        title="The hold on your account"
        lead="Your bank put a temporary hold on part of your account under the Reserve Bank of India's directions on suspected money mule accounts. Here is the notice it sent you, what you can do, and by when."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      {mine.length === 0 ? (
        <Empty>There is no hold on your account.</Empty>
      ) : (
        mine.map((h) => (
          <article key={h.hold_id} className="mb-10">
            <Attention
              tone={h.released_at ? "done" : h.explanation ? "info" : "action"}
              title={
                h.released_at
                  ? "The hold has ended"
                  : h.explanation
                    ? "The bank has your explanation and is deciding"
                    : `Explain these payments by ${formatIst(h.deadlines.find((d) => d.name === "Customer explanation")?.due ?? h.expires_at)}`
              }
              actions={
                h.released_at || h.explanation
                  ? []
                  : [
                      { label: "Send your explanation", href: "#explain", primary: true },
                      { label: "Ask for a call back", href: "#call" },
                    ]
              }
            >
              {h.released_at
                ? h.release_reason
                : h.explanation
                  ? "It must decide within 10 days of receiving your explanation."
                  : "Only the amount on hold is stopped; the rest of your balance works as usual. If you do not explain, the bank may report the payments to the police."}
            </Attention>
            <div className="mb-6 grid gap-3 sm:grid-cols-3">
              <div className="border-line border p-4">
                <p className="text-faint text-xs">On hold</p>
                <p className="mt-1 text-2xl">
                  {h.released_at ? (
                    <Money paise={h.amount} className="text-faint" />
                  ) : (
                    <Held paise={h.amount} />
                  )}
                </p>
                <p className="text-faint mt-1 text-xs">
                  {h.whole_account ? "Every debit is stopped" : "The rest of your balance works as usual"}
                </p>
              </div>
              <div className="border-line border p-4">
                <p className="text-faint text-xs">Where it stands</p>
                <p className="mt-1 text-[15px]">{statusLabel(h as unknown as Hold)}</p>
              </div>
              <div className="border-line border p-4">
                <p className="text-faint text-xs">Explain by</p>
                <p className="mt-1 text-[15px]">
                  {formatIst(h.deadlines.find((d) => d.name === "Customer explanation")?.due ?? h.expires_at)}
                </p>
              </div>
            </div>
            <div className="grid gap-8 lg:grid-cols-2">
              <section>
                <h2 className="pixel mb-3 text-lg">The bank&apos;s notice</h2>
                <pre className="bg-panel border-line border p-4 font-sans text-[14px] leading-relaxed whitespace-pre-wrap">
                  {h.customer_notice}
                </pre>
              </section>
              <section id="explain" className="scroll-mt-6">
                <h2 className="pixel mb-3 text-lg">Your explanation</h2>
                {h.explanation ? (
                  <div className="text-sm">
                    <p className="text-faint text-xs">Sent {formatIst(h.explanation_at ?? h.placed_at)}</p>
                    <p className="mt-2">{h.explanation}</p>
                    {h.decision ? (
                      <p className="mt-4">
                        The bank decided to{" "}
                        <strong className="font-normal">
                          {h.decision === "release" ? "release the hold" : "report it to the police"}
                        </strong>
                        {h.decision_reason ? `: ${h.decision_reason}` : "."}
                      </p>
                    ) : (
                      <p className="text-muted mt-4">The bank decides within 10 days of receiving it.</p>
                    )}
                  </div>
                ) : h.released_at ? (
                  <p className="text-muted text-sm">The hold has ended.</p>
                ) : (
                  <form action={myExplanationAction} className="grid gap-4">
                    <input type="hidden" name="hold_id" value={h.hold_id} />
                    <div>
                      <label htmlFor="summary" className="label">
                        What were these payments for?
                      </label>
                      <textarea
                        id="summary"
                        name="summary"
                        required
                        minLength={10}
                        maxLength={1800}
                        rows={5}
                        className="field"
                        placeholder="For example: payment from Sharma Builders for 400 bags of cement delivered on 14 October; tax invoice and delivery challan attached."
                      />
                    </div>
                    <div>
                      <label htmlFor="documents" className="label">
                        Documents (invoices, challans, agreements, salary slips)
                      </label>
                      <input
                        id="documents"
                        name="documents"
                        type="file"
                        multiple
                        accept=".pdf,.jpg,.jpeg,.png"
                        className="field"
                      />
                      <p className="text-faint mt-1 text-xs">
                        In this prototype the file names go with your explanation; the files themselves stay
                        with you.
                      </p>
                    </div>
                    <button className="button button-solid justify-self-start">Send to the bank</button>
                  </form>
                )}
              </section>
            </div>
            {!h.released_at && (
              <section id="call" className="border-line mt-10 scroll-mt-6 border p-5">
                <h2 className="pixel mb-1 text-lg">Ask the bank to call you</h2>
                <p className="text-muted mb-3 text-sm">
                  The request goes on your hold&apos;s record, so the officer handling it sees it.
                </p>
                <form action={callBackAction} className="flex flex-wrap gap-2">
                  <input type="hidden" name="hold_id" value={h.hold_id} />
                  <input
                    name="note"
                    required
                    minLength={3}
                    maxLength={500}
                    className="field min-w-64 flex-1"
                    placeholder="After 5 pm, on my registered mobile"
                    aria-label="When to call"
                  />
                  <button className="button button-solid">Request a call back</button>
                </form>
              </section>
            )}
            <section className="mt-10">
              <h2 className="pixel mb-2 text-lg">Your deadlines</h2>
              <HoldTimeline hold={h as unknown as Hold} now={clock} />
            </section>
          </article>
        ))
      )}
    </>
  );
}
