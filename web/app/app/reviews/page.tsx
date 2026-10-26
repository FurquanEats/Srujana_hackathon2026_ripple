import type { Metadata } from "next";
import Link from "next/link";

import { Notice, PageHeader } from "@/components/workspace/ui";
import { formatInr } from "@/lib/format";
import { filedGrievances, reviews } from "@/lib/gateway/source";
import { requireRole, type Outcome } from "@/lib/guard";
import { VERDICT } from "@/lib/review/labels";

export const metadata: Metadata = { title: "Evidence packs" };

export default async function ReviewsPage({ searchParams }: { searchParams: Outcome }) {
  await requireRole("grievance_officer");
  const { error } = await searchParams;
  const packs = await reviews();
  const filed = await filedGrievances();
  const confirmed = packs.reduce((s, p) => s + Object.keys(p.decisions).length, 0);
  const credits = packs.reduce((s, p) => s + p.credits.length, 0);
  return (
    <>
      <PageHeader
        title="Evidence packs"
        lead="Account holders whose credits are held send documents to explain them. Gemini reads each document into fixed fields, quoting the words behind each field; fixed rules then check those fields against the bank's own payment records and give each credit a verdict. You confirm or overrule every verdict before anything is filed."
      />
      {error && <Notice kind="error">{error}</Notice>}
      <p className="text-muted mb-6 text-sm">
        {confirmed} of {credits} credits decided by you. These are the 17 synthetic cases of the review&apos;s
        test set (eval/documents), read by {packs[0]?.model}.
      </p>
      <div className="overflow-x-auto">
        <table className="table min-w-[760px]">
          <thead>
            <tr>
              <th>Account holder</th>
              <th>Held credits</th>
              <th>Documents</th>
              <th>Verdicts</th>
              <th>Your decision</th>
              <th aria-hidden />
            </tr>
          </thead>
          <tbody>
            {packs.map((p) => (
              <tr key={p.case_id} className="row-link">
                <td>
                  <Link href={`/app/reviews/${p.case_id}`} className="stretch link">
                    {p.holder.name}
                  </Link>
                  <span className="text-faint block text-xs">
                    {p.case_id} · {p.holder.kyc.occupation ?? p.holder.kyc.business_type}
                  </span>
                </td>
                <td className="font-mono">{p.credits.map((c) => formatInr(c.amount)).join(", ")}</td>
                <td className="text-muted text-xs">{p.documents.map((d) => d.file).join(", ")}</td>
                <td>
                  {p.read ? (
                    <span className="flex flex-wrap gap-1">
                      {p.verdicts.map((v) => (
                        <span key={v.credit_id} className={`px-1.5 text-xs ${VERDICT[v.verdict].tone}`}>
                          {VERDICT[v.verdict].label}
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className="text-faint text-xs">Not read yet</span>
                  )}
                </td>
                <td className="text-xs">
                  {filed.has(p.case_id)
                    ? "Grievance filed"
                    : Object.keys(p.decisions).length === p.credits.length
                      ? "Ready to file"
                      : `${Object.keys(p.decisions).length} of ${p.credits.length} decided`}
                </td>
                <td aria-hidden className="text-right">
                  <span className="go">→</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
