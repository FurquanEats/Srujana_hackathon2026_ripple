import "server-only";

import { cookies } from "next/headers";

import { institutionName } from "@/lib/personas";
import type { DemoSession } from "@/lib/session";

import { gatewayFetch, GatewayFailure } from "./client";
import reviewPacks from "@/lib/review/reviews.json";
import type { ReviewPack } from "@/lib/review/types";

import {
  apply,
  applyLiens,
  DemoConflict,
  grievancesFiled,
  encodeChanges,
  parseChanges,
  verdictDecisions,
  type Change,
  type HoldStep,
} from "./demo-store";
import bankA from "./fixtures/bank.bank-a.json";
import bankB from "./fixtures/bank.bank-b.json";
import bankC from "./fixtures/bank.bank-c.json";
import bankD from "./fixtures/bank.bank-d.json";
import exchangeX from "./fixtures/bank.exchange-x.json";
import walletW from "./fixtures/bank.wallet-w.json";
import clockFixture from "./fixtures/clock.json";
import holdersFixture from "./fixtures/holders.json";
import victimsFixture from "./fixtures/victims.json";
import police from "./fixtures/police.json";
import type {
  AccountView,
  AuditLog,
  LienRelease,
  ThresholdApproval,
  CaseSummary,
  CustomerHold,
  HoldReport,
  PaymentCheckRequest,
  PaymentCheckResult,
  SavedCheck,
  VictimStatus,
  Hold,
  Lien,
  MuleCase,
  NoticeDetail,
  NoticeSummary,
  ShadowRun,
  Thresholds,
  Trail,
} from "./types";

/**
 * Where the workspace's data comes from. RIPPLE_GATEWAY=live calls the running network through the gateway;
 * anything else serves responses saved from a real network run (scripts/capture_web_fixtures.py), with a visitor's
 * own changes applied on top (demo-store.ts). Both return exactly the gateway contract's shapes.
 */
export const LIVE = process.env.RIPPLE_GATEWAY === "live";

const CHANGES_COOKIE = "ripple_demo_changes";
type Saved = Record<string, unknown>;
const BANKS: Record<string, Saved> = {
  "bank-a": bankA,
  "bank-b": bankB,
  "bank-c": bankC,
  "bank-d": bankD,
  "wallet-w": walletW,
  "exchange-x": exchangeX,
};

export { GatewayFailure };

function caller(s: DemoSession) {
  return { sub: s.subject ?? `demo-${s.role}`, role: s.role, member: s.member };
}

function saved<T>(s: DemoSession, route: string): T {
  const book: Saved | undefined = s.member ? BANKS[s.member] : (police as Saved);
  const value = book?.[route];
  if (value === undefined)
    throw new GatewayFailure(404, { error: "not_found", message: "Nothing is on record for this." });
  return value as T;
}

async function changes(): Promise<Change[]> {
  return parseChanges((await cookies()).get(CHANGES_COOKIE)?.value);
}

function savedFor<T>(member: string, route: string): T {
  const value = BANKS[member]?.[route];
  if (value === undefined)
    throw new GatewayFailure(404, { error: "not_found", message: "Nothing is on record for this." });
  return value as T;
}

async function bankState(s: DemoSession, member = s.member ?? "") {
  return apply(
    member,
    institutionName(member),
    savedFor<MuleCase[]>(member, "/v1/mule-cases"),
    savedFor<Hold[]>(member, "/v1/holds"),
    await changes(),
  );
}

/** The network's simulated time: live from the gateway, or the moment the saved responses were taken. */
export async function now(s: DemoSession): Promise<string> {
  if (LIVE) return (await gatewayFetch<{ now: string }>(caller(s), "/v1/clock")).now;
  return clockFixture["/v1/clock"].now;
}

export async function notices(s: DemoSession): Promise<NoticeSummary[]> {
  return LIVE ? gatewayFetch(caller(s), "/v1/notices") : saved(s, "/v1/notices");
}

export async function notice(s: DemoSession, id: string): Promise<NoticeDetail> {
  return LIVE
    ? gatewayFetch(caller(s), `/v1/notices/${encodeURIComponent(id)}`)
    : saved(s, `/v1/notices/${id}`);
}

export async function liens(s: DemoSession): Promise<Lien[]> {
  if (LIVE) return gatewayFetch(caller(s), "/v1/liens");
  return applyLiens(s.member ?? "", saved(s, "/v1/liens"), await changes());
}

export async function muleCases(s: DemoSession, includeClosed = false): Promise<MuleCase[]> {
  const all = LIVE
    ? await gatewayFetch<MuleCase[]>(caller(s), `/v1/mule-cases?include_closed=${includeClosed}`)
    : (await bankState(s)).cases;
  return includeClosed ? all : all.filter((c) => c.flags.some((f) => f.status !== "dismissed"));
}

export async function holds(s: DemoSession): Promise<Hold[]> {
  return LIVE ? gatewayFetch(caller(s), "/v1/holds") : (await bankState(s)).holds;
}

export async function thresholds(s: DemoSession): Promise<Thresholds> {
  if (LIVE) return gatewayFetch(caller(s), "/v1/detection/thresholds");
  return (await bankState(s)).thresholds ?? saved<Thresholds>(s, "/v1/detection/thresholds");
}

export async function shadowRun(s: DemoSession, budgetPerDay: number): Promise<ShadowRun | null> {
  if (LIVE) return gatewayFetch(caller(s), "/v1/detection/shadow-run", { budget_per_day: budgetPerDay });
  return saved<ShadowRun | null>(s, "/v1/detection/shadow-run");
}

export async function cases(s: DemoSession): Promise<CaseSummary[]> {
  return LIVE ? gatewayFetch(caller(s), "/v1/cases") : saved(s, "/v1/cases");
}

export async function trail(s: DemoSession, ack: string): Promise<Trail> {
  return LIVE ? gatewayFetch(caller(s), `/v1/cases/${ack}/trail`) : saved(s, `/v1/cases/${ack}/trail`);
}

/** Record a change: on the live network it is a gateway call; on saved data it joins the visitor's changes. */
async function record(s: DemoSession, change: Change, route: string, body: unknown): Promise<void> {
  if (LIVE) {
    await gatewayFetch(caller(s), route, body);
    return;
  }
  const list = [...(await changes()), change];
  try {
    if (change.k === "lien") applyLiens(change.m, savedFor(change.m, "/v1/liens"), list);
    else if (change.k !== "verdict" && change.k !== "grievance")
      apply(
        change.m,
        institutionName(change.m),
        savedFor(change.m, "/v1/mule-cases"),
        savedFor(change.m, "/v1/holds"),
        list,
      );
  } catch (error) {
    if (error instanceof DemoConflict)
      throw new GatewayFailure(409, { error: "conflict", message: error.message });
    throw error;
  }
  (await cookies()).set(CHANGES_COOKIE, encodeChanges(list), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });
}

export async function dismissCase(s: DemoSession, account: string, reason: string): Promise<void> {
  await record(
    s,
    { k: "dismiss", m: s.member ?? "", a: account, r: reason },
    `/v1/mule-cases/${account}/dismiss`,
    {
      reason,
    },
  );
}

export type HoldRequest = {
  account_number: string;
  flag_keys: string[];
  contact: string;
  whole_account: boolean;
  account_level_reason: string | null;
};

export async function placeHold(s: DemoSession, h: HoldRequest): Promise<void> {
  const id = `H${Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()}`;
  const change: Change = {
    k: "hold",
    m: s.member ?? "",
    a: h.account_number,
    keys: h.flag_keys,
    c: h.contact,
    w: h.whole_account,
    wr: h.account_level_reason,
    id,
    at: await now(s),
  };
  await record(s, change, "/v1/holds", { ...h, account_level_reason: h.account_level_reason ?? undefined });
}

export async function holdStep(
  s: DemoSession,
  holdId: string,
  stepName: HoldStep,
  body: Record<string, string>,
) {
  const change: Change = { k: "step", m: s.member ?? "", id: holdId, s: stepName, b: body, at: await now(s) };
  await record(s, change, `/v1/holds/${holdId}/${stepName}`, body);
}

export async function approveThresholds(s: DemoSession, t: Thresholds, budgetPerDay: number): Promise<void> {
  const change: Change = { k: "thresholds", m: s.member ?? "", t, at: await now(s) };
  await record(s, change, "/v1/detection/thresholds", { ...t, budget_per_day: budgetPerDay });
}

export async function playDemoStory(s: DemoSession): Promise<string> {
  if (!LIVE) {
    // The demo story's complaint in the saved run: the one filed for the retired teacher.
    const story = (police as Saved)["/v1/cases"] as CaseSummary[];
    const found = story.find((c) => c.victim_name.startsWith("Retired teacher")) ?? story[0];
    if (!found)
      throw new GatewayFailure(404, { error: "not_found", message: "The saved run has no demo story." });
    return found.ack_number;
  }
  return (await gatewayFetch<{ ack_number: string }>(caller(s), "/v1/simulation/demo-story", {})).ack_number;
}

/** Drop the visitor's changes so the saved data shows as it was taken. */
export async function resetDemo(): Promise<void> {
  (await cookies()).delete(CHANGES_COOKIE);
}

export async function audit(s: DemoSession): Promise<AuditLog> {
  return LIVE ? gatewayFetch(caller(s), "/v1/audit?limit=300") : saved(s, "/v1/audit");
}

/** Payments checked on the saved run, to open without a live network. */
export function savedChecks(s: DemoSession): SavedCheck[] {
  return LIVE ? [] : (saved<SavedCheck[] | undefined>(s, "payment-checks") ?? []);
}

export async function checkPayment(s: DemoSession, body: PaymentCheckRequest): Promise<PaymentCheckResult> {
  if (!LIVE)
    throw new GatewayFailure(409, {
      error: "conflict",
      message:
        "This copy runs on saved data, so it can only show the payments checked on the saved run. Start the network and set RIPPLE_GATEWAY=live to check any payment.",
    });
  return gatewayFetch(caller(s), "/v1/payment-check", body);
}

const CUSTOMER_KEYS = [
  "hold_id",
  "account_number",
  "holder_name",
  "amount",
  "whole_account",
  "reasons",
  "contact",
  "customer_notice",
  "placed_at",
  "status",
  "deadlines",
  "next_deadline",
  "expires_at",
  "explanation",
  "explanation_at",
  "decision",
  "decision_reason",
  "released_at",
  "release_reason",
  "reported_at",
] as const;

function customer(h: Hold): CustomerHold {
  return Object.fromEntries(CUSTOMER_KEYS.map((k) => [k, h[k]])) as CustomerHold;
}

export async function holdReports(s: DemoSession): Promise<HoldReport[]> {
  if (LIVE) return gatewayFetch(caller(s), "/v1/hold-reports");
  const reports: HoldReport[] = [];
  for (const member of Object.keys(BANKS)) {
    for (const h of (await bankState(s, member)).holds) {
      if (!h.reported_at) continue;
      reports.push({
        ...customer(h),
        member,
        member_name: institutionName(member),
        instruction: h.instruction,
        str_filed_at: h.str_filed_at,
        mule_confirmed_at: h.mule_confirmed_at,
      });
    }
  }
  return reports;
}

export async function policeInstruction(
  s: DemoSession,
  member: string,
  holdId: string,
  body: Record<string, string>,
) {
  const change: Change = {
    k: "step",
    m: member,
    id: holdId,
    s: "police-instruction",
    b: body,
    at: await now(s),
  };
  await record(s, change, `/v1/hold-reports/${member}/${holdId}/instruction`, body);
}

export async function myHolds(s: DemoSession): Promise<CustomerHold[]> {
  if (LIVE) return gatewayFetch(caller(s), "/v1/my-holds");
  return (await bankState(s)).holds.filter((h) => h.account_number === s.subject).map(customer);
}

export async function myExplanation(s: DemoSession, holdId: string, summary: string): Promise<void> {
  const change: Change = {
    k: "step",
    m: s.member ?? "",
    id: holdId,
    s: "explanation",
    b: { summary },
    at: await now(s),
  };
  await record(s, change, `/v1/my-holds/${holdId}/explanation`, { summary });
}

export async function myComplaint(s: DemoSession): Promise<VictimStatus> {
  if (LIVE) {
    const status = await gatewayFetch<Omit<VictimStatus, "victim_name" | "filed_at">>(
      caller(s),
      "/v1/my-complaint",
    );
    return { victim_name: "", filed_at: "", ...status };
  }
  const found = (victimsFixture as Record<string, VictimStatus>)[s.subject ?? ""];
  if (!found)
    throw new GatewayFailure(404, { error: "not_found", message: "No complaint with that acknowledgement." });
  // Money the police ordered back to the victim on saved data: liens released to the victim, per bank.
  const list = await changes();
  const returnedBy = new Map<string, number>();
  for (const member of Object.keys(BANKS)) {
    for (const l of applyLiens(member, savedFor(member, "/v1/liens"), list))
      if (l.ack_number === s.subject && l.returned_to_victim)
        returnedBy.set(member, (returnedBy.get(member) ?? 0) + l.amount);
  }
  const places = found.places.map((p) => {
    const returned = p.held && p.member ? (returnedBy.get(p.member) ?? 0) : 0;
    if (p.member) returnedBy.delete(p.member);
    return { ...p, returned };
  });
  return { ...found, places, returned: places.reduce((sum, p) => sum + (p.returned ?? 0), 0) };
}

/** Who can sign in as an account holder or a victim on this data. */
export function holderPersonas(): { member: string; account: string; name: string }[] {
  return Object.entries(holdersFixture as Record<string, { holder_name: string | null }>).map(([key, v]) => {
    const [member = "", account = ""] = key.split(":");
    return { member, account, name: v.holder_name ?? account };
  });
}

export function victimPersonas(): { ack: string; name: string }[] {
  return Object.entries(victimsFixture as Record<string, { victim_name: string }>).map(([ack, v]) => ({
    ack,
    name: v.victim_name,
  }));
}

export async function reviews(): Promise<
  (ReviewPack & { decisions: Record<string, { d: string; n: string; at: string }> })[]
> {
  const decided = verdictDecisions(await changes());
  return (reviewPacks as ReviewPack[]).map((p) => ({
    ...p,
    decisions: Object.fromEntries(
      p.credits.flatMap((c) => {
        const d = decided.get(`${p.case_id}:${c.credit_id}`);
        return d ? [[c.credit_id, d]] : [];
      }),
    ),
  }));
}

/** The officer confirms or overrules a verdict (PRD G4). It is kept in this browser; nothing is sent. */
export async function decideVerdict(
  s: DemoSession,
  caseId: string,
  creditId: string,
  d: "confirmed" | "overruled",
  note: string,
) {
  const change: Change = {
    k: "verdict",
    m: s.member ?? "",
    c: caseId,
    cr: creditId,
    d,
    n: note,
    at: await now(s),
  };
  const list = [...(await changes()), change];
  (await cookies()).set(CHANGES_COOKIE, encodeChanges(list), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });
}

export async function account(s: DemoSession, accountNumber: string): Promise<AccountView> {
  if (LIVE) return gatewayFetch(caller(s), `/v1/accounts/${accountNumber}`);
  const base = saved<AccountView>(s, `/v1/accounts/${accountNumber}`);
  const state = await bankState(s);
  const accountLiens = applyLiens(s.member ?? "", saved(s, "/v1/liens"), await changes()).filter(
    (l) => l.account_number === accountNumber,
  );
  const accountHolds = state.holds.filter((h) => h.account_number === accountNumber);
  const clock = await now(s);
  const onHold = accountHolds
    .filter((h) => !h.released_at && !h.whole_account && h.placed_at <= clock)
    .reduce((sum, h) => sum + h.amount, 0);
  const liened = accountLiens.filter((l) => !l.released_at).reduce((sum, l) => sum + l.amount, 0);
  return {
    ...base,
    liens: accountLiens,
    holds: accountHolds,
    flags: state.cases.filter((c) => c.account_number === accountNumber),
    liened,
    on_hold: onHold,
    available: Math.max(base.balance - liened - onHold, 0),
  };
}

export async function releaseLien(s: DemoSession, lienId: string, body: LienRelease): Promise<void> {
  const change: Change = {
    k: "lien",
    m: s.member ?? "",
    id: lienId,
    a: body.authority,
    o: body.order,
    r: body.reason,
    v: body.to_victim,
    by: s.subject ?? `demo-${s.role}`,
    at: await now(s),
  };
  await record(s, change, `/v1/liens/${lienId}/release`, body);
}

export async function policeRelease(
  s: DemoSession,
  member: string,
  lienId: string,
  body: LienRelease,
): Promise<void> {
  const change: Change = {
    k: "lien",
    m: member,
    id: lienId,
    a: body.authority,
    o: body.order,
    r: body.reason,
    v: body.to_victim,
    by: `demo-${s.role}`,
    at: await now(s),
  };
  await record(s, change, `/v1/police/liens/${member}/${lienId}/release`, body);
}

/** Lien releases visible on saved data, for the trail: lien id -> the release. */
export async function releasedLiens(): Promise<
  Map<string, { at: string; order: string; toVictim: boolean }>
> {
  if (LIVE) return new Map();
  return new Map(
    (await changes()).flatMap((c) =>
      c.k === "lien" ? [[c.id, { at: c.at, order: c.o, toVictim: c.v }] as const] : [],
    ),
  );
}

export async function holdNote(s: DemoSession, holdId: string, note: string): Promise<void> {
  const change: Change = {
    k: "note",
    m: s.member ?? "",
    id: holdId,
    n: note,
    by: `demo-${s.role}`,
    at: await now(s),
  };
  await record(s, change, `/v1/holds/${holdId}/note`, { note });
}

export async function callBack(s: DemoSession, holdId: string, note: string): Promise<void> {
  const text = `Customer asked for a call back: ${note}`.slice(0, 2000);
  const change: Change = {
    k: "note",
    m: s.member ?? "",
    id: holdId,
    n: text,
    by: `customer:${s.subject}`,
    at: await now(s),
  };
  await record(s, change, `/v1/my-holds/${holdId}/call-back`, { note });
}

export async function thresholdHistory(s: DemoSession): Promise<ThresholdApproval[]> {
  if (LIVE) return gatewayFetch(caller(s), "/v1/detection/history");
  const mine = (await changes()).flatMap((c) =>
    c.k === "thresholds" && c.m === s.member
      ? [{ settings: c.t, budget_per_day: null, approved_by: "demo-frm_analyst", approved_at: c.at }]
      : [],
  );
  return [...mine.reverse(), ...(saved<ThresholdApproval[] | undefined>(s, "/v1/detection/history") ?? [])];
}

export async function filedGrievances(): Promise<Map<string, string>> {
  return grievancesFiled(await changes());
}

export async function fileGrievance(s: DemoSession, caseId: string): Promise<void> {
  const change: Change = { k: "grievance", m: s.member ?? "", c: caseId, at: await now(s) };
  const list = [...(await changes()), change];
  (await cookies()).set(CHANGES_COOKIE, encodeChanges(list), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
  });
}

export async function fileComplaint(s: DemoSession, body: unknown): Promise<string> {
  if (!LIVE)
    throw new GatewayFailure(409, {
      error: "conflict",
      message:
        "This copy runs on saved data, so a new complaint cannot be traced. Start the network and set RIPPLE_GATEWAY=live.",
    });
  return (await gatewayFetch<{ ack_number: string }>(caller(s), "/v1/complaints", body)).ack_number;
}
