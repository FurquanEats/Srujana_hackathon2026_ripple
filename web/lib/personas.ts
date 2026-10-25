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

/** Every role in the PRD's users table, with what each one does and what it signs in as. */
export const ROLES = [
  {
    role: "nodal_officer",
    label: "Nodal officer",
    duty: "Answers CFCFRMS notices, manages liens and checks payments before they leave.",
    bank: true,
    pick: "bank",
  },
  {
    role: "frm_analyst",
    label: "FRM analyst",
    duty: "Reviews mule flags, runs temporary debit holds and their deadlines, and sets detection thresholds.",
    bank: true,
    pick: "bank",
  },
  {
    role: "grievance_officer",
    label: "Grievance officer",
    duty: "Reviews the documents an account holder sends, with Gemini's reading and fixed rules, and confirms each verdict.",
    bank: true,
    pick: "bank",
  },
  {
    role: "police_officer",
    label: "Police officer",
    duty: "Follows each complaint's money trail, and instructs banks on holds they report.",
    bank: false,
    pick: null,
  },
  {
    role: "demo",
    label: "Demo operator",
    duty: "Sees every complaint's trail and plays the demo story on the network.",
    bank: false,
    pick: null,
  },
  {
    role: "account_holder",
    label: "Account holder",
    duty: "A customer whose account has a hold: reads the notice and sends an explanation.",
    bank: true,
    pick: "holder",
  },
  {
    role: "victim",
    label: "Victim",
    duty: "Someone who reported a scam: sees what is held, where, and how it can come back.",
    bank: false,
    pick: "complaint",
  },
] as const satisfies readonly {
  role: Role;
  label: string;
  duty: string;
  bank: boolean;
  pick: "bank" | "holder" | "complaint" | null;
}[];

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

export function pickFor(role: WorkspaceRole): "bank" | "holder" | "complaint" | null {
  return ROLES.find((r) => r.role === role)?.pick ?? null;
}

export function needsBank(role: WorkspaceRole): boolean {
  return ROLES.find((r) => r.role === role)?.bank ?? false;
}
