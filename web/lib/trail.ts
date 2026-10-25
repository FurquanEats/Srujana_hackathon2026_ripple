import type { Trail, TrailAccount } from "@/lib/gateway/types";

export type Placed = { account: TrailAccount; x: number; y: number };

export const NODE_W = 210;
export const NODE_H = 78;
const COL_GAP = 70;
const ROW_GAP = 22;

/** Lay the trail out in columns by layer, each child below the last, parents centred on their children. */
export function layout(trail: Trail): { nodes: Placed[]; width: number; height: number } {
  const byLayer = new Map<number, TrailAccount[]>();
  for (const a of trail.accounts) byLayer.set(a.layer, [...(byLayer.get(a.layer) ?? []), a]);
  const layers = [...byLayer.keys()].sort((a, b) => a - b);
  const order = new Map<string, number>();
  const nodes: Placed[] = [];
  let rows = 0;
  layers.forEach((layer, col) => {
    const list = [...(byLayer.get(layer) ?? [])].sort(
      (a, b) =>
        (order.get(a.parent_id ?? "") ?? 0) - (order.get(b.parent_id ?? "") ?? 0) ||
        a.credit.at.localeCompare(b.credit.at),
    );
    list.forEach((account, row) => {
      order.set(account.notice_id, row);
      nodes.push({ account, x: col * (NODE_W + COL_GAP), y: row * (NODE_H + ROW_GAP) });
    });
    rows = Math.max(rows, list.length);
  });
  return {
    nodes,
    width: layers.length * (NODE_W + COL_GAP) - COL_GAP,
    height: rows * (NODE_H + ROW_GAP) - ROW_GAP,
  };
}

/** Every moment the replay can stop at: each credit and each exit, in order. */
export function moments(trail: Trail): string[] {
  const all = trail.accounts.flatMap((a) => [a.credit.at, ...a.exits.map((e) => e.at)]);
  return [...new Set(all)].sort();
}

/** What the replay shows at a moment: money that has arrived, been cashed out, and is held. */
export function totalsAt(trail: Trail, at: string) {
  const arrived = trail.accounts.filter((a) => a.credit.at <= at);
  const firstLayer = arrived.filter((a) => a.parent_id === null).reduce((s, a) => s + a.traced_in, 0);
  const cashedOut = arrived
    .flatMap((a) => a.exits)
    .filter((e) => e.at <= at)
    .reduce((s, e) => s + e.traced_amount, 0);
  return { reported: firstLayer, cashedOut, accounts: arrived.length };
}
