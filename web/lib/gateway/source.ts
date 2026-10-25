import "server-only";

import { cookies } from "next/headers";

import { institutionName } from "@/lib/personas";
import type { DemoSession } from "@/lib/session";

import { gatewayFetch, GatewayFailure } from "./client";
import { apply, DemoConflict, encodeChanges, parseChanges, type Change, type HoldStep } from "./demo-store";
import bankA from "./fixtures/bank.bank-a.json";
import bankB from "./fixtures/bank.bank-b.json";
import bankC from "./fixtures/bank.bank-c.json";
import bankD from "./fixtures/bank.bank-d.json";
import exchangeX from "./fixtures/bank.exchange-x.json";
import walletW from "./fixtures/bank.wallet-w.json";
import clockFixture from "./fixtures/clock.json";
import police from "./fixtures/police.json";
import type {
  CaseSummary,
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
  return { sub: `demo-${s.role}`, role: s.role, member: s.member };
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

async function bankState(s: DemoSession) {
  const member = s.member ?? "";
  return apply(
    member,
    institutionName(member),
    saved<MuleCase[]>(s, "/v1/mule-cases"),
    saved<Hold[]>(s, "/v1/holds"),
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
  return LIVE ? gatewayFetch(caller(s), "/v1/liens") : saved(s, "/v1/liens");
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
    apply(s.member ?? "", institutionName(s.member), saved(s, "/v1/mule-cases"), saved(s, "/v1/holds"), list);
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
  if (!LIVE) return "31575867494554"; // the demo story's complaint in the saved run
  return (await gatewayFetch<{ ack_number: string }>(caller(s), "/v1/simulation/demo-story", {})).ack_number;
}

/** Drop the visitor's changes so the saved data shows as it was taken. */
export async function resetDemo(): Promise<void> {
  (await cookies()).delete(CHANGES_COOKIE);
}
