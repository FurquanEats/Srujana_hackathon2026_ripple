import type { Hold } from "@/lib/gateway/types";

export const HOLD_STATUS: Record<string, string> = {
  awaiting_explanation: "Waiting for the customer's explanation",
  explanation_received: "Explanation received, decision due",
  reported_to_police: "Reported to the police",
  held_on_police_instruction: "Held on police instruction",
  released: "Released",
};

export function statusLabel(hold: Hold): string {
  return HOLD_STATUS[hold.status] ?? hold.status;
}

/** Open holds first, by their next deadline; released ones last. */
export function byNextDeadline(a: Hold, b: Hold): number {
  if (!!a.released_at !== !!b.released_at) return a.released_at ? 1 : -1;
  return (a.next_deadline ?? "9999").localeCompare(b.next_deadline ?? "9999");
}
