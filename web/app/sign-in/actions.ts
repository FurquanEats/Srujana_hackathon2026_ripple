"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { isInstitution, isWorkspaceRole, needsBank } from "@/lib/personas";
import { encodeSession, SESSION_COOKIE } from "@/lib/session";

/** Demo sign-in. It works only when RIPPLE_DEMO=1, because it asks for no password: every record is synthetic. */
export async function signIn(form: FormData): Promise<void> {
  if (process.env.RIPPLE_DEMO !== "1") redirect("/sign-in?error=disabled");
  const role = form.get("role");
  const member = form.get("member");
  if (!isWorkspaceRole(role)) redirect("/sign-in?error=role");
  const bank = needsBank(role);
  if (bank && !isInstitution(member)) redirect("/sign-in?error=member");
  (await cookies()).set(
    SESSION_COOKIE,
    encodeSession({ role, member: bank && isInstitution(member) ? member : null }),
    {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 8,
    },
  );
  redirect("/app");
}

export async function signOut(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/sign-in");
}
