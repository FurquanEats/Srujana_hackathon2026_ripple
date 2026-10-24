"use client";

import cytoscape, { type Core } from "cytoscape";
import { useEffect, useMemo, useRef } from "react";

import { money, type GraphEdge } from "@/lib/api";

export interface GraphAccount {
  id: string;
  role?: string; // victim | mule | collector | source | other | cashout
  risk?: number;
  holding?: number; // traced money still held
}

const roleColor: Record<string, string> = {
  victim: "#38bdf8",
  source: "#38bdf8",
  mule: "#f87171",
  collector: "#fb923c",
  cashout: "#a3a3a3",
  other: "#475569",
};

const CASH_OUT = /^(ATM|P2P-|VDA-|CRYPTO)/i;

/**
 * Money-flow graph laid out hop by hop from left to right. `upTo` hides payments made after that time, so a slider
 * can replay how the money moved. Frozen accounts get a thick ring.
 */
export function MoneyGraph({ edges, accounts = [], frozen = [], upTo, height = 420, currency = "INR" }: {
  edges: GraphEdge[];
  accounts?: GraphAccount[];
  frozen?: string[];
  upTo?: string;
  height?: number;
  currency?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);

  const elements = useMemo(() => {
    const info = new Map(accounts.map((a) => [a.id, a]));
    const ids = new Set(edges.flatMap((e) => [e.source, e.target]));
    const incoming = new Set(edges.map((e) => e.target));
    const nodes = [...ids].map((id) => {
      const a = info.get(id);
      const role = CASH_OUT.test(id) ? "cashout" : a?.role ?? (incoming.has(id) ? "mule" : "victim");
      const holding = a?.holding ? `\n${money(a.holding, currency)}` : "";
      return { data: { id, label: `${id}${holding}`, role, frozen: frozen.includes(id) ? 1 : 0 } };
    });
    const links = edges.map((e) => ({
      data: { id: e.txn_id, source: e.source, target: e.target, label: money(e.amount, currency), ts: e.ts },
    }));
    return [...nodes, ...links];
  }, [edges, accounts, frozen, currency]);

  // Hop depth from the accounts nobody paid (victims, sources), so money reads left to right, one column per hop.
  const positions = useMemo(() => {
    const ids = [...new Set(edges.flatMap((e) => [e.source, e.target]))];
    const targets = new Set(edges.map((e) => e.target));
    const roots = ids.filter((id) => !targets.has(id));
    const depth = new Map<string, number>((roots.length ? roots : ids.slice(0, 1)).map((id) => [id, 0]));
    const queue = [...depth.keys()];
    while (queue.length) {
      const id = queue.shift()!;
      for (const e of edges) {
        if (e.source === id && !depth.has(e.target)) {
          depth.set(e.target, depth.get(id)! + 1);
          queue.push(e.target);
        }
      }
    }
    const columns = new Map<number, string[]>();
    for (const id of ids) {
      const d = depth.get(id) ?? 0;
      columns.set(d, [...(columns.get(d) ?? []), id]);
    }
    const out: Record<string, { x: number; y: number }> = {};
    for (const [d, col] of columns) {
      col.forEach((id, i) => { out[id] = { x: d * 210, y: (i - (col.length - 1) / 2) * 80 }; });
    }
    return out;
  }, [edges]);

  useEffect(() => {
    if (!box.current) return;
    cy.current = cytoscape({
      container: box.current,
      elements,
      layout: { name: "preset", positions, fit: true, padding: 40 },
      wheelSensitivity: 0.2,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (n) => roleColor[n.data("role")] ?? roleColor.other,
            label: "data(label)",
            color: "#e2e8f0",
            "font-size": 10,
            "text-wrap": "wrap",
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: 22,
            height: 22,
          },
        },
        { selector: "node[frozen = 1]", style: { "border-width": 4, "border-color": "#34d399" } },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#64748b",
            "target-arrow-color": "#64748b",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 9,
            color: "#cbd5e1",
            "text-background-color": "#0f172a",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
          },
        },
        { selector: ".later", style: { opacity: 0.08 } },
      ],
    });
    return () => cy.current?.destroy();
  }, [elements, positions]);

  useEffect(() => {
    if (!cy.current) return;
    const limit = upTo ? new Date(upTo).getTime() : Infinity;
    cy.current.edges().forEach((e) => {
      e.toggleClass("later", new Date(e.data("ts")).getTime() > limit);
    });
  }, [upTo, elements]);

  return (
    <div>
      <div ref={box} style={{ height }} className="w-full rounded-lg bg-slate-950/70" role="img"
           aria-label={`Money-flow graph with ${edges.length} payments`} />
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
        {[["victim", "Victim or source"], ["mule", "Mule"], ["collector", "Collector"], ["cashout", "Cash-out (ATM, crypto)"]].map(
          ([role, label]) => (
            <span key={role} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: roleColor[role] }} />
              {label}
            </span>
          ),
        )}
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full border-2 border-emerald-400" /> Freeze
        </span>
      </div>
    </div>
  );
}
