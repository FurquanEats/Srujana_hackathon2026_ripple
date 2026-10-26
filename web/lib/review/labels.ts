export const VERDICT = {
  explained: { label: "Explained", tone: "bg-accent text-ink" },
  partly_explained: { label: "Partly explained", tone: "bg-amber-500 text-ink" },
  not_explained: { label: "Not explained", tone: "bg-grey-500 text-white" },
  conflicting: { label: "Conflicting", tone: "bg-red-600 text-white" },
} as const;

export const ACTION = { lift: "Lift the hold", reduce: "Reduce the hold", keep: "Keep the hold" } as const;

export const CHECKS: Record<string, string> = {
  readable: "The document can be read",
  quote_support: "Total, date and payer each have the words they were read from",
  amount_match: "The total matches the credit (or the credit net of TDS)",
  date_order: "The document is dated before the payment, or within 7 days after",
  payer_match: "The payer on the document is the remitter in the bank's payment record",
  gstin_valid: "The issuer's GSTIN has a valid check character and matches KYC",
  document_reuse: "No document explains two credits",
  business_fit: "The credit fits the holder's declared turnover or income",
};
