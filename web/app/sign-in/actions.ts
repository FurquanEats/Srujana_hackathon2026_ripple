"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { isInstitution, isWorkspaceRole, pickFor } from "@/lib/personas";
import { encodeSession, parseSession, SESSION_COOKIE, type DemoSession } from "@/lib/session";

/** Demo sign-in. It works only when RIPPLE_DEMO=1, because it asks for no password: every record is synthetic. */
export async function signIn(form: FormData): Promise<void> {
  if (process.env.RIPPLE_DEMO !== "1") redirect("/sign-in?error=disabled");
  const role = form.get("role");
  if (!isWorkspaceRole(role)) redirect("/sign-in?error=role");
  const pick = pickFor(role);
  let session: DemoSession;
  if (pick === "holder") {
    const [member, account] = String(form.get("holder") ?? "").split(":");
    if (!isInstitution(member) || !account) redirect("/sign-in?error=holder");
    session = { role, member, subject: account };
  } else if (pick === "complaint") {
    session = { role, member: null, subject: String(form.get("complaint") ?? "") };
  } else if (pick === "bank") {
    const member = form.get("member");
    if (!isInstitution(member)) redirect("/sign-in?error=member");
    session = { role, member };
  } else {
    session = { role, member: null };
  }
  const value = encodeSession(session);
  if (!parseSession(value)) redirect("/sign-in?error=role");
  (await cookies()).set(SESSION_COOKIE, value, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  redirect("/app");
}

export async function signOut(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/sign-in");
}
