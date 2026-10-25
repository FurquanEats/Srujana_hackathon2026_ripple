import type { WorkspaceRole } from "@/lib/personas";

export type NavItem = { href: string; label: string; hint: string };

/** What each role's sidebar shows. A role sees only the pages its gateway routes allow. */
export const NAV: Record<WorkspaceRole, NavItem[]> = {
  nodal_officer: [
    { href: "/app/overview", label: "Overview", hint: "What needs you today" },
    { href: "/app/notices", label: "Notices", hint: "CFCFRMS notices this bank answered" },
    { href: "/app/liens", label: "Liens", hint: "Liens on traced amounts" },
    { href: "/app/payment-check", label: "Payment check", hint: "Check a payment before it leaves" },
    { href: "/app/audit", label: "Audit log", hint: "Every action, in a tamper-evident chain" },
  ],
  frm_analyst: [
    { href: "/app/overview", label: "Overview", hint: "What needs you today" },
    { href: "/app/flags", label: "Mule flags", hint: "Accounts the detection rules flagged" },
    { href: "/app/holds", label: "Debit holds", hint: "Temporary debit holds and their deadlines" },
    { href: "/app/detection", label: "Detection", hint: "Thresholds and the 30-day shadow run" },
    { href: "/app/payment-check", label: "Payment check", hint: "Check a payment before it leaves" },
    { href: "/app/audit", label: "Audit log", hint: "Every action, in a tamper-evident chain" },
  ],
  grievance_officer: [
    { href: "/app/reviews", label: "Evidence packs", hint: "Documents reviewed against held credits" },
  ],
  police_officer: [
    { href: "/app/overview", label: "Overview", hint: "What needs you today" },
    { href: "/app/cases", label: "Cases", hint: "Complaints and their money trails" },
    { href: "/app/hold-reports", label: "Hold reports", hint: "Holds banks reported to the police" },
  ],
  demo: [
    { href: "/app/simulation", label: "Simulation", hint: "Play the demo story on the network" },
    { href: "/app/cases", label: "Cases", hint: "Complaints and their money trails" },
  ],
  account_holder: [{ href: "/app/my-hold", label: "My hold", hint: "The hold on your account" }],
  victim: [{ href: "/app/my-complaint", label: "My complaint", hint: "What is held and where" }],
};

export function homeFor(role: WorkspaceRole): string {
  return NAV[role][0]?.href ?? "/app";
}
