"use server";

import { redirect } from "next/navigation";

import type { HoldStep } from "@/lib/gateway/demo-store";
import * as source from "@/lib/gateway/source";
import { currentSession } from "@/lib/session";

/**
 * The workspace's writes. Each checks the session, validates its form, calls the data source and returns to the
 * page with the outcome. The gateway enforces the same limits again; these checks only give clearer messages.
 */
const ACCOUNT = /^[0-9A-Z]{6,20}$/;
const HOLD = /^H[0-9A-F]{16}$/;

function text(form: FormData, name: string, min: number, max: number): string | null {
  const value = String(form.get(name) ?? "").trim();
  return value.length >= min && value.length <= max ? value : null;
}

async function frm() {
  const session = await currentSession();
  if (!session || session.role !== "frm_analyst") redirect("/sign-in");
  return session;
}

function back(path: string, outcome: { error?: string; done?: string }): never {
  const query = new URLSearchParams(outcome as Record<string, string>).toString();
  redirect(`${path}?${query}`);
}

async function attempt(path: string, done: string, work: () => Promise<void>, next = path): Promise<never> {
  try {
    await work();
  } catch (error) {
    if (error instanceof source.GatewayFailure) back(path, { error: error.message });
    throw error;
  }
  back(next, { done });
}

export async function dismissFlags(form: FormData): Promise<void> {
  const session = await frm();
  const account = String(form.get("account") ?? "");
  const path = `/app/flags/${account}`;
  if (!ACCOUNT.test(account)) back("/app/flags", { error: "That is not an account number." });
  const reason = text(form, "reason", 10, 2000);
  if (!reason) back(path, { error: "Write why the flags are wrong, in at least 10 characters." });
  await attempt(
    path,
    `Dismissed the flags on ${account}.`,
    () => source.dismissCase(session, account, reason),
    "/app/flags",
  );
}

export async function placeHold(form: FormData): Promise<void> {
  const session = await frm();
  const account = String(form.get("account") ?? "");
  const path = `/app/flags/${account}`;
  if (!ACCOUNT.test(account)) back("/app/flags", { error: "That is not an account number." });
  const keys = form.getAll("flag").map(String).filter(Boolean);
  if (keys.length === 0) back(path, { error: "Choose at least one flag to hold." });
  const contact = text(form, "contact", 5, 200);
  if (!contact) back(path, { error: "Say how the customer will be told, in at least 5 characters." });
  const whole = form.get("whole") === "on";
  const reason = text(form, "whole_reason", 0, 2000);
  if (whole && (!reason || reason.length < 30))
    back(path, { error: "A hold on the whole account needs a written reason of at least 30 characters." });
  await attempt(
    path,
    "Hold placed. The customer notice went out at once.",
    () =>
      source.placeHold(session, {
        account_number: account,
        flag_keys: keys,
        contact,
        whole_account: whole,
        account_level_reason: whole ? reason : null,
      }),
    "/app/holds",
  );
}

const STEPS: Record<string, { step: HoldStep; fields: Record<string, [number, number]>; done: string }> = {
  explanation: {
    step: "explanation",
    fields: { summary: [1, 2000] },
    done: "Recorded the customer's explanation.",
  },
  decision: {
    step: "decision",
    fields: { decision: [6, 7], reason: [1, 2000] },
    done: "Recorded the bank's decision.",
  },
  instruction: {
    step: "police-instruction",
    fields: { instruction: [7, 8], authority: [3, 200] },
    done: "Recorded the police instruction.",
  },
  confirm: {
    step: "confirm-mule",
    fields: { grounds: [1, 2000] },
    done: "Confirmed as a mule. The STR draft is ready.",
  },
  str: { step: "str-filed", fields: { reference: [3, 64] }, done: "Recorded the STR as filed." },
};

export async function holdAction(form: FormData): Promise<void> {
  const session = await frm();
  const id = String(form.get("hold_id") ?? "");
  if (!HOLD.test(id)) back("/app/holds", { error: "That is not a hold." });
  const path = `/app/holds/${id}`;
  const spec = STEPS[String(form.get("action") ?? "")];
  if (!spec) back(path, { error: "Unknown action." });
  const body: Record<string, string> = {};
  for (const [name, [min, max]] of Object.entries(spec.fields)) {
    const value = text(form, name, min, max);
    if (!value) back(path, { error: "Fill in every field." });
    body[name] = value;
  }
  if (body.decision && !["release", "report"].includes(body.decision))
    back(path, { error: "Choose release or report." });
  if (body.instruction && !["release", "continue"].includes(body.instruction))
    back(path, { error: "Choose release or continue." });
  await attempt(path, spec.done, () => source.holdStep(session, id, spec.step, body));
}

export async function approveThresholds(form: FormData): Promise<void> {
  const session = await frm();
  const num = (name: string) => Number(form.get(name));
  const t = {
    pass_through_minutes: num("pass_through_minutes"),
    new_senders: num("new_senders"),
    profile_multiple: num("profile_multiple"),
    dormant_days: num("dormant_days"),
    cash_out_minutes: num("cash_out_minutes"),
  };
  const budget = num("budget_per_day");
  if (Object.values(t).some((v) => !Number.isFinite(v) || v <= 0) || !(budget > 0))
    back("/app/detection", { error: "Every threshold must be a positive number." });
  await attempt("/app/detection", "New thresholds approved. They apply from the next posting batch.", () =>
    source.approveThresholds(session, t, budget),
  );
}

export async function playDemo(): Promise<void> {
  const session = await currentSession();
  if (!session || session.role !== "demo") redirect("/sign-in");
  let ack = "";
  try {
    ack = await source.playDemoStory(session);
  } catch (error) {
    if (error instanceof source.GatewayFailure) back("/app/simulation", { error: error.message });
    throw error;
  }
  redirect(`/app/cases/${ack}`);
}

export async function policeInstructionAction(form: FormData): Promise<void> {
  const session = await currentSession();
  if (!session || session.role !== "police_officer") redirect("/sign-in");
  const member = String(form.get("member") ?? "");
  const id = String(form.get("hold_id") ?? "");
  const instruction = String(form.get("instruction") ?? "");
  const authority = text(form, "authority", 3, 200);
  if (!/^[a-z]+-[a-z]$/.test(member) || !HOLD.test(id))
    back("/app/hold-reports", { error: "That is not a reported hold." });
  if (!["release", "continue"].includes(instruction) || !authority)
    back("/app/hold-reports", { error: "Choose an instruction and name the police authority." });
  await attempt("/app/hold-reports", "Instruction sent to the bank.", () =>
    source.policeInstruction(session, member, id, { instruction, authority }),
  );
}

export async function myExplanationAction(form: FormData): Promise<void> {
  const session = await currentSession();
  if (!session || session.role !== "account_holder") redirect("/sign-in");
  const id = String(form.get("hold_id") ?? "");
  const summary = text(form, "summary", 10, 2000);
  const documents = form
    .getAll("documents")
    .filter((f): f is File => f instanceof File && f.size > 0)
    .map((f) => f.name);
  if (!HOLD.test(id)) back("/app/my-hold", { error: "That is not your hold." });
  if (!summary) back("/app/my-hold", { error: "Explain the transactions in at least 10 characters." });
  const full = documents.length ? `${summary} Documents: ${documents.join(", ")}.`.slice(0, 2000) : summary;
  await attempt("/app/my-hold", "Your explanation reached the bank. It will decide within 10 days.", () =>
    source.myExplanation(session, id, full),
  );
}

export async function verdictAction(form: FormData): Promise<void> {
  const session = await currentSession();
  if (!session || session.role !== "grievance_officer") redirect("/sign-in");
  const caseId = String(form.get("case") ?? "");
  const credit = String(form.get("credit") ?? "");
  const decision = String(form.get("decision") ?? "");
  const note = text(form, "note", 0, 1000) ?? "";
  const path = `/app/reviews/${caseId}`;
  if (!/^D\d{2}$/.test(caseId) || !/^C\d{1,2}$/.test(credit))
    back("/app/reviews", { error: "Unknown evidence pack." });
  if (decision !== "confirmed" && decision !== "overruled")
    back(path, { error: "Confirm or overrule the verdict." });
  if (decision === "overruled" && note.length < 10)
    back(path, { error: "Say why you overrule the verdict, in at least 10 characters." });
  await source.decideVerdict(session, caseId, credit, decision, note);
  back(path, {
    done: decision === "confirmed" ? `Verdict for ${credit} confirmed.` : `Verdict for ${credit} overruled.`,
  });
}
