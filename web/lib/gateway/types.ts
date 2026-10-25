/**
 * The gateway's shapes, exactly as "03 Gateway API contract" (version 1.1) defines them. Amounts are integer paise
 * and times are ISO 8601 in UTC. They match ripple_core.messages.
 */

export type Rail = "upi" | "imps" | "neft" | "rtgs" | "internal";
export type ExitMode = "atm" | "aeps" | "pos" | "cheque" | "crypto" | "loan_repayment" | "card_repayment";
export type Role =
  | "nodal_officer"
  | "frm_analyst"
  | "grievance_officer"
  | "police_officer"
  | "account_holder"
  | "victim"
  | "demo";

export type Payment = { rail: Rail; reference: string; amount: number; at: string };

/** An account number with its IFSC, or a UPI ID. */
export type AccountRef = { ifsc: string | null; account_number: string | null; vpa: string | null };

export type OnwardHop = { payment: Payment; to: AccountRef; traced_amount: number };

export type Exit = {
  mode: ExitMode;
  reference: string;
  at: string;
  amount: number;
  traced_amount: number;
  identifier: string;
  location: string | null;
};

export type ExitDetail = { mode: ExitMode; reference: string; identifier: string; location: string | null };

export type Me = { sub: string; role: Role; member: string | null; member_name: string | null };

export type Clock = { now: string };

export type NetworkMember = {
  id: string;
  name: string;
  kind: "bank" | "wallet" | "exchange" | "hub";
  bank_code: string | null;
};

export type NoticeSummary = {
  notice_id: string;
  ack_number: string;
  layer: number;
  account_number: string | null;
  holder_name: string | null;
  received_at: string;
  status: "matched" | "not_found";
  reason: string | null;
  traced_in: number;
  held: number;
  lien_id: string | null;
  onward_count: number;
  exit_count: number;
};

export type StatementLine = {
  txn_id: string;
  at: string;
  direction: "credit" | "debit";
  rail: Rail;
  reference: string;
  amount: number;
  counterparty: AccountRef | null;
  exit: ExitDetail | null;
  victim_money: Record<string, number>;
};

export type NoticeDetail = {
  summary: NoticeSummary;
  credit: Payment;
  legal_basis: string;
  onward: OnwardHop[];
  exits: Exit[];
  statement: StatementLine[];
};

export type Lien = {
  lien_id: string;
  account_number: string;
  holder_name: string | null;
  ack_number: string;
  amount: number;
  basis: string;
  placed_at: string;
  released_at: string | null;
};

export type CaseTotals = {
  reported: number;
  held: number;
  cashed_out: number;
  off_network: number;
  not_found: number;
  waiting: number;
  complete: boolean;
};

export type CaseSummary = CaseTotals & { ack_number: string; victim_name: string; filed_at: string };

export type TrailAccount = {
  notice_id: string;
  parent_id: string | null;
  layer: number;
  member: string | null;
  account: AccountRef;
  holder_name: string | null;
  credit: Payment;
  traced_in: number;
  state: "answered" | "not_found" | "off_network" | "waiting";
  held: number;
  lien_id: string | null;
  exits: Exit[];
  reason: string | null;
};

export type Trail = CaseTotals & { ack_number: string; accounts: TrailAccount[] };

export type GatewayError = {
  error: "unauthenticated" | "forbidden" | "not_found" | "conflict" | "invalid" | "upstream_error";
  message: string;
};

export type MuleFlag = {
  key: string;
  rule: string;
  title: string;
  reason: string;
  amount: number;
  at: string;
  cited_txns: string[];
  credit_txns: string[];
  status: "open" | "dismissed" | "held";
  dismissed_reason: string | null;
};

export type MuleCase = {
  account_number: string;
  holder_name: string | null;
  declared_profile: string | null;
  declared_annual_income: number | null;
  priority: "high" | "medium" | "low";
  priority_reason: string;
  reported: boolean;
  rules: string[];
  flags: MuleFlag[];
  flagged_amount: number;
  first_at: string;
  last_at: string;
  active_hold_id: string | null;
};

export type HoldDeadline = {
  name: string;
  rule: string;
  due: string;
  met_at: string | null;
  state: "open" | "met" | "lapsed" | "missed" | string;
};

export type HoldStatus =
  | "awaiting_explanation"
  | "explanation_received"
  | "reported_to_police"
  | "held_on_police_instruction"
  | "released";

export type Hold = {
  hold_id: string;
  account_number: string;
  holder_name: string | null;
  amount: number;
  whole_account: boolean;
  account_level_reason: string | null;
  credit_txns: string[];
  reasons: string[];
  contact: string;
  customer_notice: string;
  placed_at: string;
  placed_by: string;
  status: HoldStatus | string;
  deadlines: HoldDeadline[];
  next_deadline: string | null;
  expires_at: string;
  explanation: string | null;
  explanation_at: string | null;
  decision: string | null;
  decision_reason: string | null;
  reported_at: string | null;
  instruction: string | null;
  released_at: string | null;
  release_reason: string | null;
  mule_confirmed_at: string | null;
  str_due: string | null;
  str_draft: Record<string, unknown> | null;
  str_filed_at: string | null;
  str_reference: string | null;
  compliance_breach: string | null;
};

export type Thresholds = {
  pass_through_minutes: number;
  new_senders: number;
  profile_multiple: number;
  dormant_days: number;
  cash_out_minutes: number;
};

export type ShadowRow = {
  value: number;
  accounts_flagged: number;
  flags_per_day: number;
  known_bad_flagged: number;
};

export type ShadowRun = {
  accounts: number;
  budget_per_day: number;
  expected_flags_per_day: number;
  known_bad: number;
  proposal: Thresholds;
  rules: { rule: string; title: string; chosen: number; rows: ShadowRow[] }[];
  note?: string | null;
  [extra: string]: unknown;
};
