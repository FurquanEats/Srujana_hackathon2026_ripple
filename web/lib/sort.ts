import type { CaseSummary, MuleCase, NoticeSummary } from "@/lib/gateway/types";

/**
 * Orderings for the officer's lists. "Severity" is the default everywhere: what can still be saved, or what breaks
 * a rule, comes first. Ties fall back to the larger amount, then the newest.
 */
export const CASE_SORTS = [
  { value: "severity", label: "Severity" },
  { value: "held", label: "Most money held" },
  { value: "reported", label: "Largest reported" },
  { value: "newest", label: "Newest first" },
  { value: "oldest", label: "Oldest first" },
] as const;

/** A complaint's severity: still being traced first (money may still move), then money held and not yet returned. */
function caseSeverity(c: CaseSummary): number {
  return (c.complete ? 0 : 2) + (c.held > 0 ? 1 : 0);
}

export function sortCases(list: CaseSummary[], sort: string | undefined): CaseSummary[] {
  const by: Record<string, (a: CaseSummary, b: CaseSummary) => number> = {
    severity: (a, b) => caseSeverity(b) - caseSeverity(a) || b.held - a.held || b.reported - a.reported,
    held: (a, b) => b.held - a.held,
    reported: (a, b) => b.reported - a.reported,
    newest: (a, b) => b.filed_at.localeCompare(a.filed_at),
    oldest: (a, b) => a.filed_at.localeCompare(b.filed_at),
  };
  return [...list].sort(by[sort ?? "severity"] ?? by.severity);
}

export const NOTICE_SORTS = [
  { value: "severity", label: "Severity" },
  { value: "held", label: "Largest lien" },
  { value: "traced", label: "Most victim money in" },
  { value: "layer", label: "Closest to the victim" },
  { value: "newest", label: "Newest first" },
] as const;

/** A notice's severity: an account reported again (police direction may be needed), then a lien in force, then nearer the victim. */
export function sortNotices(
  list: NoticeSummary[],
  sort: string | undefined,
  repeats: Map<string, number>,
): NoticeSummary[] {
  const repeat = (n: NoticeSummary) => ((repeats.get(n.account_number ?? "") ?? 0) > 1 ? 1 : 0);
  const by: Record<string, (a: NoticeSummary, b: NoticeSummary) => number> = {
    severity: (a, b) =>
      repeat(b) - repeat(a) ||
      Number(b.held > 0) - Number(a.held > 0) ||
      a.layer - b.layer ||
      b.held - a.held,
    held: (a, b) => b.held - a.held,
    traced: (a, b) => b.traced_in - a.traced_in,
    layer: (a, b) => a.layer - b.layer,
    newest: (a, b) => b.received_at.localeCompare(a.received_at),
  };
  return [...list].sort(by[sort ?? "severity"] ?? by.severity);
}

export const FLAG_SORTS = [
  { value: "severity", label: "Severity (priority)" },
  { value: "amount", label: "Largest flagged amount" },
  { value: "newest", label: "Most recent activity" },
] as const;

const PRIORITY = { high: 0, medium: 1, low: 2 } as const;

export function sortFlags(list: MuleCase[], sort: string | undefined): MuleCase[] {
  const by: Record<string, (a: MuleCase, b: MuleCase) => number> = {
    severity: (a, b) => PRIORITY[a.priority] - PRIORITY[b.priority] || b.flagged_amount - a.flagged_amount,
    amount: (a, b) => b.flagged_amount - a.flagged_amount,
    newest: (a, b) => b.last_at.localeCompare(a.last_at),
  };
  return [...list].sort(by[sort ?? "severity"] ?? by.severity);
}
