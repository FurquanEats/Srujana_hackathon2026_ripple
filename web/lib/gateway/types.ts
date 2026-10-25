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
