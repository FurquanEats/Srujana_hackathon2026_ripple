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
  src_handle?: string | null;
  device_id?: string | null;
  location?: string | null;
  channel?: string | null;
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
  persona?: string | null;
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
  str_due?: string | null;
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
  by_rule?: Partial<Record<"haircut" | "fifo" | "libr", number>>;
  hold_low?: number | null;
  hold_high?: number | null;
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
  recoverable_low?: number | null;
  recoverable_high?: number | null;
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

export interface ConsortiumResult {
  mode: string;
  laundering_payments: number;
  caught: number;
  recall: number | null;
  alerts: number;
  precision: number | null;
  false_alerts: number;
}

export interface ConsortiumReport {
  dataset: string;
  rows: number;
  member_banks: string[];
  results: ConsortiumResult[];
  note: string;
}

export interface RedTeamRun {
  generated_at: string;
  plans_tried: number;
  evading_plans: number;
  caught_share: number;
  rounds: { round: number; plans: number; evaded: number; caught_share: number; best: { description: string; evaded: boolean; max_probability: number; laundered: number } }[];
  blind_spots: { description: string; laundered: number; max_probability: number }[];
  note: string;
}

export interface MotifRule {
  feature: string;
  text: string;
  low: number;
  high: number;
  background_share: number;
}

export interface LearnedPattern {
  motif_id: string;
  name: string;
  learned_from: string;
  learned_at: string;
  rules: MotifRule[];
  steps: string[];
  example_txn_ids: string[];
  background_events: number;
  background_days: number;
  background_matches: number;
  false_alarms_per_day: number;
  lead_hours?: number | null;
  deployed: boolean;
  hits: number;
  recent_hits: string[];
}

export interface LearnRequest {
  case_id?: string;
  account?: string;
  from_ts?: string | null;
  amount?: number | null;
  name?: string;
}

export interface OneShotReport {
  generated_at: string;
  example: { plan: string; peak_probability: number; transactions: number };
  motif: {
    name: string;
    constraints: { feature: string; text: string; background_share: number }[];
    steps: string[];
    background_events: number;
    background_days: number;
    false_alarms_per_day: number;
    lead_hours: number | null;
  };
  generalisation: { plans: number; caught_without: number; caught_with: number; missed_without: number; of_missed_caught_with: number };
  adaptive_red_team: Record<"without" | "with", { plans_tried: number; evading_plans: number; caught_share: number }>;
  unseen_bank: {
    seed: number;
    days: number;
    transactions: number;
    without: { legit_alerts: number; motif_alerts_on_legit: number };
    with: { legit_alerts: number; motif_alerts_on_legit: number };
  };
  notes: string[];
}

export interface OneShotIbmType {
  type: string;
  example_attempt: number;
  rules?: string[];
  expected_false_alarms_per_day?: number;
  error?: string;
  attempts_after?: number;
  caught_same_type?: number;
  caught_same_type_in_time?: number;
  attempts_after_any_type?: number;
  caught_any_type?: number;
  legit_matches_per_day?: number;
  days_live?: number;
}

export interface OneShotIbmReport {
  generated_at: string;
  dataset: string;
  rows: number;
  days: number;
  max_false_alarms_per_day: number;
  per_type: OneShotIbmType[];
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
  consortium: () => request<ConsortiumReport>("/consortium"),
  redteam: () => request<{ latest: RedTeamRun; before: RedTeamRun | null }>("/redteam"),
  inject: (kind: string) => request<InjectResult>(`/inject/${kind}`, post()),
  trace: (account: string, from_ts?: string, amount?: number) =>
    request<InterdictionPlan>("/trace", post({ account, from_ts: from_ts || null, amount: amount ?? null })),
  motifs: () => request<LearnedPattern[]>("/motifs"),
  learn: (body: LearnRequest) => request<LearnedPattern>("/motifs/learn", post(body)),
  deploy: (id: string) => request<LearnedPattern>(`/motifs/${encodeURIComponent(id)}/deploy`, post()),
  retire: (id: string) => request<LearnedPattern>(`/motifs/${encodeURIComponent(id)}/retire`, post()),
  oneshot: () => request<OneShotReport>("/oneshot"),
  oneshotIbm: () => request<OneShotIbmReport>("/oneshot/ibm"),
};

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const inrCompact = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1, minimumFractionDigits: 0 });
const usdCompact = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1, minimumFractionDigits: 0 });

/** Full amount. INR uses lakh grouping (₹11,40,000); USD is kept for IBM AML evaluation data. */
export const money = (amount: number, currency = "INR") => (currency === "INR" ? inr : usd).format(amount);
/** Short amount for chart axes and graph labels: ₹11.4L, ₹1.3Cr, $1.1M. */
export const moneyShort = (amount: number, currency = "INR") => (currency === "INR" ? inrCompact : usdCompact).format(amount);
export const pct = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`;
/** A model probability as a percentage that never rounds up to a certain-looking 100%. */
export const prob = (p: number) => (p >= 0.995 && p < 1 ? ">99%" : pct(p));
export const time = (ts: string) =>
  new Date(ts).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
export const clock = (ts: string) => new Date(ts).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
