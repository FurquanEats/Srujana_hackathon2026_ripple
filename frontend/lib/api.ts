// Mirrors backend/ripple/schema.py. Regenerate from the API's OpenAPI schema when it changes.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Tier = "Critical" | "Review" | "Watch";

export interface CaseSummary {
  case_id: string;
  tier: Tier;
  probability: number;
  amount_at_risk: number;
  expected_loss: number;
  accounts: number;
  transactions: number;
  typologies: string[];
  opened_at: string;
  updated_at: string;
  status: string;
}

export async function getCases(budget = 50): Promise<CaseSummary[]> {
  const res = await fetch(`${API_URL}/cases?budget=${budget}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET /cases failed with ${res.status}`);
  return res.json();
}

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

export const formatINR = (amount: number) => inr.format(amount);
