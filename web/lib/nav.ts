import type { WorkspaceRole } from "@/lib/personas";

export type NavItem = { href: string; label: string; hint: string };

/** What each role's sidebar shows. A role sees only the pages its gateway routes allow. */
export const NAV: Record<WorkspaceRole, NavItem[]> = {
  nodal_officer: [
    { href: "/app/notices", label: "Notices", hint: "CFCFRMS notices this bank answered" },
    { href: "/app/liens", label: "Liens", hint: "Liens on traced amounts" },
  ],
  frm_analyst: [
    { href: "/app/flags", label: "Mule flags", hint: "Accounts the detection rules flagged" },
    { href: "/app/holds", label: "Debit holds", hint: "Temporary debit holds and their deadlines" },
    { href: "/app/detection", label: "Detection", hint: "Thresholds and the 30-day shadow run" },
  ],
  police_officer: [{ href: "/app/cases", label: "Cases", hint: "Complaints and their money trails" }],
  demo: [
    { href: "/app/cases", label: "Cases", hint: "Complaints and their money trails" },
    { href: "/app/simulation", label: "Simulation", hint: "Play the demo story on the network" },
  ],
};

export function homeFor(role: WorkspaceRole): string {
  return NAV[role][0]?.href ?? "/app";
}
