import "server-only";

import { redirect } from "next/navigation";

import type { WorkspaceRole } from "@/lib/personas";
import { currentSession, type DemoSession } from "@/lib/session";

/** The signed-in session, if its role may open this page; otherwise back to sign-in. */
export async function requireRole(...roles: WorkspaceRole[]): Promise<DemoSession> {
  const session = await currentSession();
  if (!session || !roles.includes(session.role)) redirect("/sign-in");
  return session;
}

export type Outcome = Promise<{ error?: string; done?: string }>;
