/**
 * Changes a visitor makes while the workspace runs on saved gateway responses (no live network): dismissing a
 * flag, placing and moving a temporary debit hold, approving thresholds. They are kept in a cookie and applied
 * over the saved responses with the same rules the bank node enforces (ripple_node.holds), so the demo behaves
 * like the real thing. Nothing here runs when the workspace talks to a live gateway.
 */
import { formatInr } from "@/lib/format";

import type { Hold, HoldDeadline, MuleCase, Thresholds } from "./types";

export type Change =
  | { k: "dismiss"; m: string; a: string; r: string }
  | {
      k: "hold";
      m: string;
      a: string;
      keys: string[];
      c: string;
      w: boolean;
      wr: string | null;
      id: string;
      at: string;
    }
  | { k: "step"; m: string; id: string; s: HoldStep; b: Record<string, string>; at: string }
  | { k: "thresholds"; m: string; t: Thresholds; at: string }
  | { k: "verdict"; m: string; c: string; cr: string; d: "confirmed" | "overruled"; n: string; at: string };

export type HoldStep = "explanation" | "decision" | "police-instruction" | "confirm-mule" | "str-filed";

export const MAX_CHANGES = 40;
const DAY = 86_400_000;

export class DemoConflict extends Error {}

function plus(iso: string, days: number): string {
  return new Date(new Date(iso).getTime() + days * DAY).toISOString();
}

function longDate(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(iso));
}

/** Seven working days after `iso`, skipping Saturdays and Sundays (PML Rules, rule 8(3)); holidays not modelled. */
export function workingDaysAfter(iso: string, days: number): string {
  let d = new Date(iso);
  let left = days;
  while (left > 0) {
    d = new Date(d.getTime() + DAY);
    const weekday = d.getUTCDay();
    if (weekday !== 0 && weekday !== 6) left -= 1;
  }
  return d.toISOString();
}

const STEPS = new Set(["explanation", "decision", "police-instruction", "confirm-mule", "str-filed"]);

/** A hand-edited cookie can only drop its own entries, never break the page. */
function isChange(value: unknown): value is Change {
  if (typeof value !== "object" || value === null) return false;
  const c = value as Record<string, unknown>;
  if (typeof c.m !== "string") return false;
  const str = (v: unknown) => typeof v === "string";
  switch (c.k) {
    case "dismiss":
      return str(c.a) && str(c.r);
    case "hold":
      return (
        str(c.a) &&
        Array.isArray(c.keys) &&
        c.keys.every(str) &&
        str(c.c) &&
        str(c.id) &&
        str(c.at) &&
        typeof c.w === "boolean"
      );
    case "step":
      return str(c.id) && STEPS.has(c.s as string) && typeof c.b === "object" && c.b !== null && str(c.at);
    case "thresholds":
      return typeof c.t === "object" && c.t !== null && str(c.at);
    case "verdict":
      return str(c.c) && str(c.cr) && (c.d === "confirmed" || c.d === "overruled") && str(c.n) && str(c.at);
    default:
      return false;
  }
}

export function parseChanges(value: string | undefined): Change[] {
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(Buffer.from(value, "base64url").toString("utf8"));
    return Array.isArray(parsed) ? parsed.filter(isChange).slice(-MAX_CHANGES) : [];
  } catch {
    return [];
  }
}

export function encodeChanges(changes: Change[]): string {
  return Buffer.from(JSON.stringify(changes.slice(-MAX_CHANGES)), "utf8").toString("base64url");
}

function deadlines(hold: Hold): HoldDeadline[] {
  const explanationDue = plus(hold.placed_at, 20);
  const decisionDue = hold.explanation_at ? plus(hold.explanation_at, 10) : plus(hold.placed_at, 30);
  const decidedAt = hold.decision ? (hold.reported_at ?? hold.released_at) : null;
  const list: HoldDeadline[] = [
    {
      name: "Customer notified",
      rule: "Annex III Step 2: at once when the customer is reached digitally",
      due: hold.placed_at,
      met_at: hold.placed_at,
      state: "met",
    },
    {
      name: "Customer explanation",
      rule: "Annex III Step 3: 20 days from the hold",
      due: explanationDue,
      met_at: hold.explanation_at,
      state: hold.explanation_at ? "met" : "open",
    },
    {
      name: "Bank decision",
      rule: "Annex III Step 4: 10 days from an explanation, or 30 days from the hold without one",
      due: decisionDue,
      met_at: decidedAt,
      state: decidedAt ? "met" : "open",
    },
  ];
  if (hold.reported_at) {
    list.push({
      name: "Police instruction",
      rule: "Annex III Step 5: release on the 31st day from the report unless the police say otherwise",
      due: plus(hold.reported_at, 30),
      met_at: hold.instruction ? hold.reported_at : null,
      state: hold.instruction || hold.released_at ? "met" : "open",
    });
  }
  list.push({
    name: "Maximum duration",
    rule: "Annex III: no temporary debit hold lasts more than 60 days",
    due: hold.expires_at,
    met_at: hold.released_at,
    state: hold.released_at ? "met" : "open",
  });
  if (hold.str_due) {
    list.push({
      name: "STR filed with FIU-IND",
      rule: "PML Rules, rule 8(3): 7 working days from forming the suspicion",
      due: hold.str_due,
      met_at: hold.str_filed_at,
      state: hold.str_filed_at ? "met" : "open",
    });
  }
  return list;
}

function refresh(hold: Hold): Hold {
  const list = deadlines(hold);
  const open = list.filter((d) => d.state === "open").map((d) => d.due);
  open.sort();
  const breach =
    hold.mule_confirmed_at && !hold.str_filed_at && hold.str_due && hold.str_due < new Date().toISOString()
      ? "A confirmed mule without a filed STR: the bank is not compliant (Amendment Directions para 4(1))."
      : null;
  return {
    ...hold,
    deadlines: list,
    next_deadline: hold.released_at ? null : (open[0] ?? null),
    compliance_breach: breach,
  };
}

function notice(
  bankName: string,
  c: MuleCase,
  amount: number,
  at: string,
  reasons: string[],
  contact: string,
): string {
  const ending = c.account_number.slice(-4);
  return [
    `Dear ${c.holder_name ?? "customer"},`,
    "",
    `${bankName} has placed a temporary hold on debits of ${formatInr(amount)} from your account ending ${ending}, from ${longDate(at)}. The bank has done this under the Reserve Bank of India's directions on suspected money mule accounts, because of these transactions: ${reasons.join(" ")}`,
    "",
    "You can still receive money, and you can use any balance that is not on hold.",
    "",
    `To have the hold removed, send the bank an explanation of these transactions, with any documents that support it, such as invoices, agreements or salary slips, by ${longDate(plus(at, 20))}. The bank will decide within 10 days of receiving your explanation. If no explanation reaches the bank, it will decide by ${longDate(plus(at, 30))}, and it may then report the transactions to the police through the National Cybercrime Reporting Portal.`,
    "",
    `Contact: ${contact}`,
  ].join("\n");
}

export type Applied = { cases: MuleCase[]; holds: Hold[]; thresholds: Thresholds | null };

/** Apply one institution's changes over its saved cases and holds. Throws DemoConflict as the node would 409. */
export function apply(
  member: string,
  bankName: string,
  savedCases: MuleCase[],
  savedHolds: Hold[],
  changes: Change[],
): Applied {
  let cases = structuredClone(savedCases);
  let holds = structuredClone(savedHolds);
  let thresholds: Thresholds | null = null;
  for (const change of changes) {
    if (change.m !== member) continue;
    if (change.k === "dismiss") {
      cases = cases.map((c) =>
        c.account_number === change.a
          ? {
              ...c,
              flags: c.flags.map((f) =>
                f.status === "open" ? { ...f, status: "dismissed", dismissed_reason: change.r } : f,
              ),
            }
          : c,
      );
    } else if (change.k === "thresholds") {
      thresholds = change.t;
    } else if (change.k === "verdict") {
      continue; // read by the review pages through `verdictDecisions`
    } else if (change.k === "hold") {
      const c = cases.find((x) => x.account_number === change.a);
      if (!c) throw new DemoConflict("This account has no open flags.");
      if (c.active_hold_id)
        throw new DemoConflict("This account already has an active temporary debit hold.");
      const flags = c.flags.filter((f) => change.keys.includes(f.key) && f.status === "open");
      if (flags.length === 0) throw new DemoConflict("Choose at least one open flag to hold.");
      const amount = flags.reduce((sum, f) => Math.max(sum, f.amount), 0);
      const reasons = flags.map((f) => f.reason);
      const hold: Hold = {
        hold_id: change.id,
        account_number: c.account_number,
        holder_name: c.holder_name,
        amount,
        whole_account: change.w,
        account_level_reason: change.wr,
        credit_txns: [...new Set(flags.flatMap((f) => f.credit_txns))],
        reasons,
        contact: change.c,
        customer_notice: notice(bankName, c, amount, change.at, reasons, change.c),
        placed_at: change.at,
        placed_by: "demo-frm_analyst",
        status: "awaiting_explanation",
        deadlines: [],
        next_deadline: null,
        expires_at: plus(change.at, 60),
        explanation: null,
        explanation_at: null,
        decision: null,
        decision_reason: null,
        reported_at: null,
        instruction: null,
        released_at: null,
        release_reason: null,
        mule_confirmed_at: null,
        str_due: null,
        str_draft: null,
        str_filed_at: null,
        str_reference: null,
        compliance_breach: null,
      };
      holds = [refresh(hold), ...holds];
      cases = cases.map((x) =>
        x.account_number === c.account_number
          ? {
              ...x,
              active_hold_id: change.id,
              flags: x.flags.map((f) => (change.keys.includes(f.key) ? { ...f, status: "held" } : f)),
            }
          : x,
      );
    } else {
      const index = holds.findIndex((h) => h.hold_id === change.id);
      const current = holds[index];
      if (!current) throw new DemoConflict("No such hold at this bank.");
      const next = step(current, change.s, change.b, change.at);
      holds[index] = refresh(next);
      if (next.released_at) {
        cases = cases.map((x) => (x.active_hold_id === next.hold_id ? { ...x, active_hold_id: null } : x));
      }
    }
  }
  return { cases, holds, thresholds };
}

function step(h: Hold, s: HoldStep, b: Record<string, string>, at: string): Hold {
  switch (s) {
    case "explanation":
      if (h.status !== "awaiting_explanation")
        throw new DemoConflict("The bank already has this customer's explanation.");
      return { ...h, status: "explanation_received", explanation: b.summary ?? "", explanation_at: at };
    case "decision": {
      if (h.status !== "awaiting_explanation" && h.status !== "explanation_received")
        throw new DemoConflict("The bank has already decided on this hold.");
      if (b.decision === "report" && h.status === "awaiting_explanation" && at <= plus(h.placed_at, 20))
        throw new DemoConflict(
          `the customer has until ${longDate(plus(h.placed_at, 20))} to explain; report only after an explanation or once that time has run out`,
        );
      if (b.decision === "release")
        return {
          ...h,
          status: "released",
          decision: "release",
          decision_reason: b.reason ?? "",
          released_at: at,
          release_reason: b.reason ?? "",
        };
      return {
        ...h,
        status: "reported_to_police",
        decision: "report",
        decision_reason: b.reason ?? "",
        reported_at: at,
      };
    }
    case "police-instruction":
      if (h.status !== "reported_to_police")
        throw new DemoConflict("only a hold reported to the police can take a police instruction");
      if (b.instruction === "release")
        return {
          ...h,
          status: "released",
          instruction: "release",
          released_at: at,
          release_reason: `Released on the instruction of ${b.authority}.`,
        };
      return { ...h, status: "held_on_police_instruction", instruction: "continue" };
    case "confirm-mule":
      if (h.mule_confirmed_at) throw new DemoConflict("This account is already confirmed as a mule.");
      return {
        ...h,
        mule_confirmed_at: at,
        str_due: workingDaysAfter(at, 7),
        str_draft: {
          report_type: "STR",
          grounds_of_suspicion: [...h.reasons, b.grounds ?? ""],
          suspicion_formed_at: at,
        },
      };
    case "str-filed":
      if (!h.mule_confirmed_at) throw new DemoConflict("Confirm the account as a mule before filing an STR.");
      if (h.str_filed_at) throw new DemoConflict("The STR is already filed.");
      return { ...h, str_filed_at: at, str_reference: b.reference ?? "" };
  }
}

/** The grievance officer's confirmations, latest per credit: "D01:C1" -> decision. */
export function verdictDecisions(
  changes: Change[],
): Map<string, { d: "confirmed" | "overruled"; n: string; at: string }> {
  const out = new Map<string, { d: "confirmed" | "overruled"; n: string; at: string }>();
  for (const c of changes) if (c.k === "verdict") out.set(`${c.c}:${c.cr}`, { d: c.d, n: c.n, at: c.at });
  return out;
}
