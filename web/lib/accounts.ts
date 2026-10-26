import type { AccountRef } from "@/lib/gateway/types";

/** The institution behind an IFSC's first four letters, on the simulated network (network.toml's bank codes). */
const BANK_CODES: Record<string, string> = {
  BKAA: "Navodaya Bank",
  BKBB: "Meridian Bank",
  BKCC: "Pragati Bank",
  BKDD: "Sangam Bank",
  WLTW: "PaySetu",
  XCHX: "CoinKosh",
};

/** An account as officers read it: its institution and number ("Pragati Bank · 5669175002"), or the UPI ID. */
export function accountText(ref: AccountRef | null): string {
  if (!ref) return "Not on the network";
  if (ref.account_number) {
    const bank = ref.ifsc ? BANK_CODES[ref.ifsc.slice(0, 4).toUpperCase()] : undefined;
    return bank
      ? `${bank} · ${ref.account_number}`
      : ref.ifsc
        ? `${ref.account_number} (${ref.ifsc})`
        : ref.account_number;
  }
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
