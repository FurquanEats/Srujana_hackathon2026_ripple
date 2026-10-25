import "server-only";

import { cookies } from "next/headers";

import {
  isInstitution,
  isWorkspaceRole,
  needsBank,
  type InstitutionId,
  type WorkspaceRole,
} from "@/lib/personas";

/**
 * The demo sign-in: the visitor picks a role and an institution, and the choice lives in an http-only cookie.
 * There are no passwords because every record in the workspace is synthetic. The gateway still checks the role
 * and the institution on every request, so a hand-edited cookie gets no further than the sign-in page allows.
 */
export type DemoSession = { role: WorkspaceRole; member: InstitutionId | null };

export const SESSION_COOKIE = "ripple_session";

export function parseSession(value: string | undefined): DemoSession | null {
  if (!value) return null;
  try {
    const parsed: unknown = JSON.parse(Buffer.from(value, "base64url").toString("utf8"));
    if (typeof parsed !== "object" || parsed === null) return null;
    const { role, member } = parsed as Record<string, unknown>;
    if (!isWorkspaceRole(role)) return null;
    if (needsBank(role)) return isInstitution(member) ? { role, member } : null;
    return { role, member: null };
  } catch {
    return null;
  }
}

export function encodeSession(session: DemoSession): string {
  return Buffer.from(JSON.stringify(session), "utf8").toString("base64url");
}

export async function currentSession(): Promise<DemoSession | null> {
  const jar = await cookies();
  return parseSession(jar.get(SESSION_COOKIE)?.value);
}
