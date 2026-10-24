import { Suspense } from "react";

import { formatINR, getCases, type Tier } from "@/lib/api";

const tierStyle: Record<Tier, string> = {
  Critical: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
  Review: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  Watch: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
};

async function CaseTable() {
  let cases;
  try {
    cases = await getCases();
  } catch (e) {
    return (
      <p role="alert" className="mt-8 rounded border border-red-300 p-4 text-sm">
        Could not reach the Ripple API ({e instanceof Error ? e.message : String(e)}). Start it with{" "}
        <code>uvicorn ripple.api.main:app</code> in backend/.
      </p>
    );
  }

  return (
    <table className="mt-8 w-full text-left text-sm">
      <caption className="sr-only">Open cases</caption>
      <thead className="border-b opacity-70">
        <tr>
          <th className="py-2">Case</th>
          <th>Tier</th>
          <th className="text-right">Probability</th>
          <th className="text-right">Expected loss</th>
          <th className="text-right">Accounts</th>
          <th className="pl-6">Typologies</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr key={c.case_id} className="border-b last:border-0">
            <td className="py-3 font-mono">{c.case_id}</td>
            <td>
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${tierStyle[c.tier]}`}>{c.tier}</span>
            </td>
            <td className="text-right tabular-nums">{c.probability.toFixed(2)}</td>
            <td className="text-right tabular-nums">{formatINR(c.expected_loss)}</td>
            <td className="text-right tabular-nums">{c.accounts}</td>
            <td className="pl-6">{c.typologies.join(", ")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function CaseQueue() {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Ripple</h1>
      <p className="mt-2 text-sm opacity-70">
        Open cases ranked by expected loss. Scores are risk indicators for an analyst to review, not findings of fraud.
      </p>
      <Suspense fallback={<p className="mt-8 text-sm opacity-70">Loading cases…</p>}>
        <CaseTable />
      </Suspense>
    </main>
  );
}
