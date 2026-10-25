import type { Metadata } from "next";

import { Empty, PageHeader } from "@/components/workspace/ui";
import { formatInr, formatIst } from "@/lib/format";
import { audit } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "Audit log" };

const ACTIONS: Record<string, string> = {
  notice_answered: "Answered a CFCFRMS notice",
  "hold.place": "Placed a temporary debit hold",
  "hold.explanation": "Recorded the customer's explanation",
  "hold.decide.release": "Decided to release the hold",
  "hold.decide.report": "Reported the hold to the police",
  "hold.instruction.continue": "Recorded a police instruction to continue",
  "hold.instruction.release": "Recorded a police instruction to release",
  "hold.confirm_mule": "Confirmed the account as a mule",
  "hold.str_filed": "Recorded the STR as filed",
  "hold.release_at_deadline": "Released the hold at its deadline",
  "flags.dismiss": "Dismissed mule flags",
  "thresholds.approve": "Approved detection thresholds",
};

function describe(record: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(record)) {
    if (v === null || v === undefined || typeof v === "object") continue;
    const value = typeof v === "number" && /amount|held|traced/.test(k) ? formatInr(v) : String(v);
    parts.push(`${k.replaceAll("_", " ")}: ${value}`);
  }
  return parts.join(" · ");
}

export default async function AuditPage() {
  const session = await requireRole("nodal_officer", "frm_analyst");
  const log = await audit(session);
  return (
    <>
      <PageHeader
        title="Audit log"
        lead="Every action this bank's Ripple node took, newest first. The log is append-only: each entry carries the hash of the one before it, so changing any past entry breaks the chain from that point (RBI Annex III keeps records for 5 years from the hold)."
      />
      <p
        className={`mb-6 inline-flex items-center gap-2 border px-3 py-2 text-sm ${log.broken_at === null ? "border-accent" : "border-red-500 text-red-500"}`}
      >
        <span aria-hidden className={`size-2 ${log.broken_at === null ? "bg-accent" : "bg-red-500"}`} />
        {log.broken_at === null
          ? "Hash chain intact from the first entry."
          : `Hash chain broken at entry ${log.broken_at}.`}
      </p>
      {log.entries.length === 0 ? (
        <Empty>No actions yet.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="table min-w-[760px]">
            <thead>
              <tr>
                <th>#</th>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {log.entries.map((e) => (
                <tr key={e.seq}>
                  <td className="text-faint font-mono">{e.seq}</td>
                  <td className="text-muted text-xs whitespace-nowrap">{formatIst(e.at)}</td>
                  <td className="font-mono text-xs">{e.actor}</td>
                  <td>
                    {ACTIONS[e.action] ?? e.action}
                    <span className="text-muted mt-1 block text-xs">{describe(e.record)}</span>
                  </td>
                  <td className="text-faint font-mono text-xs" title={e.hash}>
                    {e.hash.slice(0, 10)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
