import type { AccountRef } from "@/lib/gateway/types";

/** An account as officers write it: the number with its IFSC, or the UPI ID. */
export function accountText(ref: AccountRef | null): string {
  if (!ref) return "Not on the network";
  if (ref.account_number) return ref.ifsc ? `${ref.account_number} (${ref.ifsc})` : ref.account_number;
  return ref.vpa ?? "Unknown";
}

export const RAIL: Record<string, string> = {
  upi: "UPI",
  imps: "IMPS",
  neft: "NEFT",
  rtgs: "RTGS",
  internal: "Transfer",
};

export const EXIT: Record<string, string> = {
  atm: "ATM withdrawal",
  aeps: "AePS withdrawal",
  pos: "Card payment",
  cheque: "Cheque",
  crypto: "Crypto purchase",
  loan_repayment: "Loan repayment",
  card_repayment: "Card repayment",
};
