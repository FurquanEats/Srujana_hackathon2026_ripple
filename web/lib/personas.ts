import type { Role } from "@/lib/gateway/types";

/** The institutions in network.toml that a bank role can belong to. */
export const INSTITUTIONS = [
  { id: "bank-a", name: "Bank A, a public sector bank", short: "Bank A" },
  { id: "bank-b", name: "Bank B, a private bank", short: "Bank B" },
  { id: "bank-c", name: "Bank C, a small finance bank", short: "Bank C" },
  { id: "bank-d", name: "Bank D, a co-operative bank", short: "Bank D" },
  { id: "wallet-w", name: "Wallet W, a prepaid wallet issuer", short: "Wallet W" },
  { id: "exchange-x", name: "Exchange X, a crypto exchange on CFCFRMS", short: "Exchange X" },
] as const;

export type InstitutionId = (typeof INSTITUTIONS)[number]["id"];

/** The roles the workspace offers today, with what each one does. Grievance, account holder and victim come later. */
export const ROLES = [
  {
    role: "nodal_officer",
    label: "Nodal officer",
    duty: "Answers CFCFRMS notices and manages liens on traced amounts.",
    bank: true,
  },
  {
    role: "frm_analyst",
    label: "FRM analyst",
    duty: "Reviews mule flags, places temporary debit holds and sets detection thresholds.",
    bank: true,
  },
  {
    role: "police_officer",
    label: "Police officer",
    duty: "Follows each complaint's money trail across every institution.",
    bank: false,
  },
  {
    role: "demo",
    label: "Demo operator",
    duty: "Sees every complaint's trail and plays the demo story on the network.",
    bank: false,
  },
] as const satisfies readonly { role: Role; label: string; duty: string; bank: boolean }[];

export type WorkspaceRole = (typeof ROLES)[number]["role"];

export function roleLabel(role: Role): string {
  return ROLES.find((r) => r.role === role)?.label ?? role;
}

export function institutionName(id: string | null, short = false): string {
  const found = INSTITUTIONS.find((i) => i.id === id);
  if (!found) return id ?? "Off network";
  return short ? found.short : found.name;
}

export function isInstitution(id: unknown): id is InstitutionId {
  return INSTITUTIONS.some((i) => i.id === id);
}

export function isWorkspaceRole(role: unknown): role is WorkspaceRole {
  return ROLES.some((r) => r.role === role);
}

export function needsBank(role: WorkspaceRole): boolean {
  return ROLES.find((r) => r.role === role)?.bank ?? false;
}
