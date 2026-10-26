import type { Metadata } from "next";
import Link from "next/link";

import { Explainer } from "@/components/workspace/attention";
import { Metric, Section } from "@/components/workspace/cards";
import { Held, Money, PageHeader } from "@/components/workspace/ui";
import { formatInr } from "@/lib/format";
import { cases } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";
import results from "@/lib/review/results.json";
import { VERDICT } from "@/lib/review/labels";

export const metadata: Metadata = { title: "Results" };

type Row = {
  case: string;
  credit: string;
  title: string;
  expected: keyof typeof VERDICT;
  got: keyof typeof VERDICT;
  correct: boolean;
  unsafe: boolean;
};

export default async function ResultsPage() {
  const session = await requireRole("demo");
  const list = await cases(session);
  const reported = list.reduce((s, c) => s + c.reported, 0);
  const held = list.reduce((s, c) => s + c.held, 0);
  const cashed = list.reduce((s, c) => s + c.cashed_out, 0);
  const r = results as unknown as {
    model: string;
    coverage: { documents_read: number; documents: number; cases_reviewed: number; cases: number };
    credits: number;
    correct: number;
    unsafe_explained: number;
    field_accuracy: Record<string, number | null>;
    rows: Row[];
  };
  return (
    <>
      <PageHeader
        title="Results"
        lead="What Ripple measured on the simulated network and the synthetic document set. Every figure comes from a run, not an estimate."
      />
      <Section title="Tracing">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Complaints traced" value={list.length} href="/app/cases" />
          <Metric label="Money reported" value={<Money paise={reported} />} />
          <Metric
            label="Held for victims"
            value={<Held paise={held} />}
            note={`${Math.round((held / Math.max(reported, 1)) * 100)}% of what was reported`}
          />
          <Metric label="Cashed out before any notice" value={<Money paise={cashed} />} />
        </div>
        <p className="text-muted mt-4 max-w-3xl text-sm">
          The demo story traced across six institutions in under a second (0.3 s on the demo network), every
          bank answering automatically. Held, cashed out, off network, not found and waiting add up to the
          amount reported on every trail.
        </p>
      </Section>
      <Section title="Document review">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Credits with the right verdict" value={`${r.correct} of ${r.credits}`} />
          <Metric
            label="Bad documents marked explained"
            value={r.unsafe_explained}
            note="The target is zero"
          />
          <Metric
            label="Documents read"
            value={`${r.coverage.documents_read} of ${r.coverage.documents}`}
            note={
              r.coverage.documents_read < r.coverage.documents
                ? "Free-tier quota ran out"
                : "Every document in the set"
            }
          />
          <Metric label="Model" value={<span className="text-base">{r.model}</span>} />
        </div>
        <p className="text-muted mt-4 text-sm">
          Fields read exactly as printed:{" "}
          {Object.entries(r.field_accuracy)
            .filter(([, v]) => v !== null)
            .map(([k, v]) => `${k.replace("_", " ")} ${Math.round((v ?? 0) * 100)}%`)
            .join(", ")}
          .
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="table min-w-[680px]">
            <thead>
              <tr>
                <th>Case</th>
                <th>What it tests</th>
                <th>Expected</th>
                <th>Ripple said</th>
              </tr>
            </thead>
            <tbody>
              {r.rows.map((row) => (
                <tr key={`${row.case}-${row.credit}`}>
                  <td className="font-mono text-xs">
                    {row.case} {row.credit}
                  </td>
                  <td>{row.title}</td>
                  <td>{VERDICT[row.expected].label}</td>
                  <td className={row.correct ? "" : "text-red-600"}>
                    {VERDICT[row.got].label}
                    {row.correct ? "" : " (miss)"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
      <Explainer title="How these were measured">
        <p>
          Tracing: a month of ordinary Indian payments from the simulator (355 accounts, 26,101 postings), the
          PRD&apos;s demo story and three more scam shapes, each complaint filed on the simulated CFCFRMS.
        </p>
        <p>
          Review: the 17 synthetic cases in eval/documents, read by Gemini and decided by fixed rules; scored
          against each case&apos;s ground truth. See{" "}
          <Link className="link" href="/app/cases">
            Cases
          </Link>{" "}
          for every trail. Amounts: {formatInr(reported)} reported in all.
        </p>
      </Explainer>
    </>
  );
}
