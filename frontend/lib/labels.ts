// Readable names for the reason codes the engine emits (backend/ripple/detectors, graph.py, consortium.py).
// Presentation only: these never add evidence, they name the signal the backend already reported.

const LABELS: Record<string, string> = {
  pass_through: "Pass-through",
  fan_in: "Fan-in",
  fan_in_out: "Fan-in then out",
  fan_out: "Fan-out",
  fan_out_burst: "Fan-out burst",
  scatter_gather: "Scatter-gather",
  gather_scatter: "Gather-scatter",
  temporal_cycle: "Money cycle",
  cycle: "Money cycle",
  cash_structuring: "Cash structuring",
  device_takeover: "Device takeover",
  coerced_transfer: "Coerced transfer",
  rapid_cash_out: "Rapid cash-out",
  baseline_amount: "Unusual amount",
  baseline_hour: "Unusual hour",
  baseline_velocity_in: "Unusual inflow pace",
  baseline_velocity_out: "Unusual outflow pace",
  community: "Linked to other alerts",
  proximity: "Near other alerts",
  consortium: "Seen at another bank",
};

/**
 * Context signals describe how unusual a payment is rather than a laundering pattern. The engine caps cases built
 * only from these at Watch, so the UI keeps them visually quiet.
 */
const CONTEXT = new Set(["baseline_amount", "baseline_hour", "baseline_velocity_in", "baseline_velocity_out", "community", "proximity", "consortium"]);

export const reasonLabel = (code: string) =>
  code.startsWith("motif:") ? `Learned pattern ${code.slice(6)}`
    : LABELS[code] ?? code.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const isContextSignal = (code: string) => CONTEXT.has(code) || code.startsWith("baseline");

export const LAYER_LABEL: Record<string, string> = {
  detector: "Pattern detector",
  baseline: "Behavioural baseline",
  graph: "Graph layer",
  model: "ML model",
};

/** True when every signal on a case is a context signal: an unusual-but-possibly-honest customer. */
export const contextOnly = (codes: string[]) => codes.length > 0 && codes.every(isContextSignal);
