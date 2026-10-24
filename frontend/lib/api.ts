// Mirrors backend/ripple/schema.py. Keep the two in step when the API contract changes.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = API_URL.replace(/^http/, "ws") + "/ws/stream";

export type Tier = "Critical" | "Review" | "Watch";
export type Layer = "detector" | "baseline" | "graph" | "model";

export interface Reason {
  layer: Layer;
  code: string;
  text: string;
  strength: number;
  txn_ids: string[];
  counterfactual?: string | null;
}

export interface ScoredTransaction {
  txn_id: string;
  ts: string;
  src_account: string;
  dst_account: string;
  amount: number;
  currency: string;
  rail: string;
  device_id?: string | null;
  location?: string | null;
  probability: number;
  confidence: number;
  layer_scores: Record<Layer, number>;
  reasons: Reason[];
  is_alert: boolean;
  case_id?: string | null;
}

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

export interface GraphNode {
  id: string;
  label: string;
  role: string;
  risk: number;
}

export interface GraphEdge {
  txn_id: string;
  source: string;
  target: string;
  amount: number;
  ts: string;
}

export interface AccountProfile {
  account_id: string;
  opened_days_ago?: number | null;
  median_amount_30d?: number | null;
  txns_30d?: number | null;
  devices: string[];
}

export interface ShapValue {
  feature: string;
  value: number;
  contribution: number;
}

export interface CaseDetail extends CaseSummary {
  reasons: Reason[];
  shap: ShapValue[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  timeline: ScoredTransaction[];
  profiles: AccountProfile[];
  narrative?: string | null;
}

export interface TaintHolding {
  account_id: string;
  received: number;
  sent: number;
  tainted: number;
  tainted_share: number;
}

export interface FreezeAction {
  account_id: string;
  recoverable: number;
  collateral_cost: number;
  reason: string;
}

export interface RecoveryPoint {
  ts: string;
  recoverable: number;
  escaped: number;
}

export interface InterdictionPlan {
  case_id: string;
  as_of: string;
  stolen: number;
  victims: string[];
  holdings: TaintHolding[];
  freeze: FreezeAction[];
  recoverable_now: number;
  escaped: number;
  first_alert_at?: string | null;
  recoverable_at_first_alert?: number | null;
  recoverable_share_at_first_alert?: number | null;
  timeline: RecoveryPoint[];
  edges: GraphEdge[];
  method: string;
}

export interface MetricRow {
  name: string;
  precision: number;
  recall: number;
  pr_auc?: number | null;
  precision_at_50?: number | null;
}

export interface BudgetPoint {
  alerts_per_day: number;
  recall: number;
  precision: number;
  value_caught_share: number;
}

export interface RecoverableRow {
  name: string;
  attempts: number;
  alerted_share: number;
  median_recoverable: number;
  mean_recoverable: number;
}

export interface EvalReport {
  dataset: string;
  split: string;
  generated_at: string;
  overall: MetricRow;
  baseline: MetricRow;
  ablation: MetricRow[];
  per_typology: MetricRow[];
  budget_curve: BudgetPoint[];
  suggested_budget: number;
  throughput_tps?: number | null;
  p95_latency_ms?: number | null;
  money_recoverable?: RecoverableRow[];
  notes: string[];
}

export interface InjectResult {
  kind: string;
  at: string;
  txn_ids: string[];
  victim_account?: string | null;
  victim_paid_at?: string | null;
}

export interface StreamEvent {
  type: "txn" | "case" | "stats";
  txn?: ScoredTransaction;
  case?: CaseSummary;
  stats?: Record<string, number>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const detail = await res.json().then((b) => b.detail).catch(() => res.statusText);
    throw new Error(typeof detail === "string" ? detail : `${path} failed with ${res.status}`);
  }
  return res.json();
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  health: () => request<{ status: string; source: string; stats?: Record<string, number> }>("/health"),
  cases: (budget = 50, status = "open") => request<CaseSummary[]>(`/cases?budget=${budget}&status=${status}`),
  case: (id: string) => request<CaseDetail>(`/cases/${encodeURIComponent(id)}`),
  interdiction: (id: string) => request<InterdictionPlan>(`/cases/${encodeURIComponent(id)}/interdiction`),
  feedback: (id: string, verdict: "confirmed" | "dismissed") =>
    request<{ weights_before: Record<Layer, number>; weights_after: Record<Layer, number>; requeued: number }>(
      `/cases/${encodeURIComponent(id)}/feedback`,
      post({ verdict }),
    ),
  eval: () => request<EvalReport>("/eval"),
  inject: (kind: string) => request<InjectResult>(`/inject/${kind}`, post()),
  trace: (account: string, from_ts?: string, amount?: number) =>
    request<InterdictionPlan>("/trace", post({ account, from_ts: from_ts || null, amount: amount ?? null })),
};

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const money = (amount: number, currency = "INR") => (currency === "INR" ? inr : usd).format(amount);
export const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;
export const time = (ts: string) =>
  new Date(ts).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
