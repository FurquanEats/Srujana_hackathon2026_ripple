"use client";

import cytoscape, { type Core } from "cytoscape";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { money, time, type GraphEdge } from "@/lib/api";

import { Button, Icon } from "./ui";

export interface GraphAccount {
  id: string;
  role?: string; // victim | mule | collector | source | other | cashout
  risk?: number;
  holding?: number; // traced money still held
}

// Each role differs in shape as well as colour, so the graph reads without colour vision.
const ROLE: Record<string, { color: string; shape: cytoscape.Css.NodeShape; label: string }> = {
  victim: { color: "#0b6e63", shape: "round-rectangle", label: "Victim or source" },
  mule: { color: "#15171a", shape: "ellipse", label: "Mule account" },
  collector: { color: "#6a4c93", shape: "diamond", label: "Collector" },
  cashout: { color: "#9a9da3", shape: "hexagon", label: "Cash-out (ATM, crypto)" },
  other: { color: "#9a9da3", shape: "ellipse", label: "Other" },
};
const roleOf = (r: string) => (r === "source" ? "victim" : ROLE[r] ? r : "other");

const CASH_OUT = /^(ATM|P2P-|VDA-|CRYPTO)/i;
const FREEZE = "#0b6e63";

/**
 * Money-flow graph laid out hop by hop from left to right. `upTo` hides payments made after that time, so a slider
 * can replay how the money moved. Accounts recommended for a hold get a thick teal ring and a label.
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
  // Phones start on the readable payments list; the graph stays one tap away.
  const [view, setView] = useState<"graph" | "list">(() =>
    typeof window !== "undefined" && window.matchMedia("(max-width: 639px)").matches ? "list" : "graph");

  const elements = useMemo(() => {
    const info = new Map(accounts.map((a) => [a.id, a]));
    const ids = new Set(edges.flatMap((e) => [e.source, e.target]));
    const incoming = new Set(edges.map((e) => e.target));
    const nodes = [...ids].map((id) => {
      const a = info.get(id);
      const role = roleOf(CASH_OUT.test(id) ? "cashout" : a?.role ?? (incoming.has(id) ? "mule" : "victim"));
      const rank = frozen.indexOf(id);
      const lines = [id];
      if (a?.holding) lines.push(`holds ${money(a.holding, currency)}`);
      if (rank >= 0) lines.push(`Hold #${rank + 1}`);
      return { data: { id, label: lines.join("\n"), role, frozen: rank >= 0 ? 1 : 0 } };
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
      col.forEach((id, i) => { out[id] = { x: d * 240, y: (i - (col.length - 1) / 2) * 96 }; });
    }
    return out;
  }, [edges]);

  useEffect(() => {
    if (view !== "graph" || !box.current) return;
    // On touch screens a pannable canvas swallows page scrolling, so the graph stays fitted and static there.
    const coarse = typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;
    cy.current = cytoscape({
      container: box.current,
      elements,
      layout: { name: "preset", positions, fit: true, padding: 48 },
      wheelSensitivity: 0.2,
      maxZoom: 2.5,
      minZoom: 0.2,
      userPanningEnabled: !coarse,
      userZoomingEnabled: !coarse,
      boxSelectionEnabled: false,
      autoungrabify: coarse,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (n: cytoscape.NodeSingular) => ROLE[n.data("role")].color,
            shape: (n: cytoscape.NodeSingular) => ROLE[n.data("role")].shape,
            label: "data(label)",
            color: "#15171a",
            "font-family": "IBM Plex Mono, ui-monospace, monospace",
            "font-size": 11,
            "font-weight": 500,
            "text-wrap": "wrap",
            "text-valign": "bottom",
            "text-margin-y": 6,
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.92,
            "text-background-padding": "2px",
            "text-background-shape": "roundrectangle",
            width: 24,
            height: 24,
          },
        },
        { selector: "node[frozen = 1]", style: { "border-width": 5, "border-color": FREEZE, "border-opacity": 1, width: 28, height: 28, "font-weight": 600 } },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#c2c4c8",
            "target-arrow-color": "#9a9da3",
            "target-arrow-shape": "triangle",
            "arrow-scale": 1.1,
            "curve-style": "bezier",
            label: "data(label)",
            "font-family": "IBM Plex Sans Variable, system-ui, sans-serif",
            "font-size": 10,
            "font-weight": 600,
            color: "#15171a",
            "text-background-color": "#eef3f1",
            "text-background-opacity": 1,
            "text-background-padding": "3px",
            "text-background-shape": "roundrectangle",
            "text-rotation": "autorotate",
          },
        },
        { selector: ".later", style: { opacity: 0.12 } },
        { selector: "edge.latest", style: { width: 3.5, "line-color": FREEZE, "target-arrow-color": FREEZE } },
      ],
    });
    // Small trails would otherwise be blown up to fill the box; cap the fitted zoom so labels stay at reading size.
    if (cy.current.zoom() > 1.1) { cy.current.zoom(1.1); cy.current.center(); }
    return () => { cy.current?.destroy(); cy.current = null; };
  }, [elements, positions, view]);

  useEffect(() => {
    const g = cy.current;
    if (!g) return;
    const limit = upTo ? new Date(upTo).getTime() : Infinity;
    g.edges().forEach((e) => {
      const t = new Date(e.data("ts")).getTime();
      e.toggleClass("later", t > limit);
      e.toggleClass("latest", upTo !== undefined && t === limit);
    });
    g.nodes().forEach((n) => {
      const links = n.connectedEdges();
      n.toggleClass("later", links.length > 0 && links.filter(".later").length === links.length);
    });
  }, [upTo, elements, view]);

  const shown = useMemo(() => {
    const limit = upTo ? new Date(upTo).getTime() : Infinity;
    return edges.filter((e) => new Date(e.ts).getTime() <= limit);
  }, [edges, upTo]);

  const roles = useMemo(() => new Set(elements.filter((e) => "role" in e.data).map((e) => (e.data as { role: string }).role)), [elements]);

  return (
    <div className="min-w-0">
      <div className="no-print mb-3 flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label="Money-flow view" className="inline-flex rounded-md border border-line-strong bg-surface p-0.5">
          {(["graph", "list"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
                    className={`inline-flex min-h-9 items-center gap-1.5 rounded px-3 text-sm font-semibold ${view === v ? "bg-navy text-white" : "text-muted hover:bg-sunken"}`}>
              <Icon name={v === "graph" ? "graph" : "list"} className="h-4 w-4" />
              {v === "graph" ? "Graph" : "Payments list"}
            </button>
          ))}
        </div>
        {view === "graph" && (
          <Button size="sm" variant="ghost" onClick={() => { const g = cy.current; if (!g) return; g.fit(undefined, 48); if (g.zoom() > 1.1) { g.zoom(1.1); g.center(); } }}>Fit to view</Button>
        )}
      </div>

      {view === "graph" ? (
        <>
          <div ref={box} style={{ height }} className="w-full rounded-lg border border-line bg-[#fbfaf7]" role="img"
               aria-label={`Money-flow graph: ${shown.length} of ${edges.length} payments shown across ${roles.size} account roles. Use the payments list for a text version.`} />
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted" aria-label="Graph legend">
            {(["victim", "mule", "collector", "cashout"] as const).map((r) => (
              <li key={r} className="flex items-center gap-1.5">
                <LegendShape role={r} />{ROLE[r].label}
              </li>
            ))}
            <li className="flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-3.5 w-3.5 rounded-full border-[3px] bg-surface" style={{ borderColor: FREEZE }} />
              Recommended hold (not yet placed)
            </li>
            <li className="flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-0.5 w-5 rounded" style={{ background: "#c2c4c8" }} />
              Payment, labelled with amount
            </li>
          </ul>
        </>
      ) : (
        <PaymentList edges={shown} total={edges.length} frozen={frozen} currency={currency} />
      )}
    </div>
  );
}

function LegendShape({ role }: { role: keyof typeof ROLE }) {
  const c = ROLE[role].color;
  const shapes: Record<string, ReactNode> = {
    victim: <rect x="1" y="2" width="12" height="10" rx="3" fill={c} />,
    mule: <circle cx="7" cy="7" r="6" fill={c} />,
    collector: <path d="M7 0.5 13.5 7 7 13.5 0.5 7Z" fill={c} />,
    cashout: <path d="M3.5 1h7L14 7l-3.5 6h-7L0 7Z" fill={c} />,
  };
  return <svg viewBox="0 0 14 14" className="h-3.5 w-3.5" aria-hidden>{shapes[role]}</svg>;
}

function PaymentList({ edges, total, frozen, currency }: { edges: GraphEdge[]; total: number; frozen: string[]; currency: string }) {
  if (edges.length === 0) return <p className="text-sm text-muted">No payments up to this point in the replay.</p>;
  const hold = (id: string) => frozen.includes(id) && (
    <span className="ml-1 rounded bg-teal-soft px-1 text-[11px] font-semibold text-teal-strong">hold</span>
  );
  return (
    <div>
      <p className="mb-2 text-xs text-subtle">{edges.length} of {total} payments, in time order.</p>
      {/* Phone: stacked rows. Wider: a table. */}
      <ol className="divide-y divide-line rounded-lg border border-line sm:hidden">
        {edges.map((e) => (
          <li key={e.txn_id} className="px-3 py-2.5 text-sm">
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-semibold tabular-nums">{money(e.amount, currency)}</span>
              <span className="text-xs text-subtle">{time(e.ts)}</span>
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-1 font-mono text-xs text-muted">
              {e.source}{hold(e.source)} <Icon name="arrowRight" className="h-3 w-3" /> {e.target}{hold(e.target)}
            </div>
            <div className="mt-0.5 font-mono text-[11px] text-subtle">{e.txn_id}</div>
          </li>
        ))}
      </ol>
      <div className="hidden max-h-[420px] overflow-auto rounded-lg border border-line sm:block">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-sunken text-xs text-muted">
            <tr><th scope="col" className="px-3 py-2 font-semibold">Time</th><th scope="col" className="px-3 py-2 font-semibold">Transaction</th><th scope="col" className="px-3 py-2 font-semibold">From</th><th scope="col" className="px-3 py-2 font-semibold">To</th><th scope="col" className="px-3 py-2 text-right font-semibold">Amount</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {edges.map((e) => (
              <tr key={e.txn_id}>
                <td className="whitespace-nowrap px-3 py-2 text-muted">{time(e.ts)}</td>
                <td className="px-3 py-2 font-mono text-xs text-subtle">{e.txn_id}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">{e.source}{hold(e.source)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">{e.target}{hold(e.target)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right font-semibold tabular-nums">{money(e.amount, currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Replay the money moving: step through payments in time order, or play them back automatically. */
export function ReplayControls({ edges, step, onStep }: { edges: GraphEdge[]; step: number | null; onStep: (s: number | null) => void }) {
  const [playing, setPlaying] = useState(false);
  const last = edges.length - 1;
  const current = step ?? last;

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => {
      const next = current + 1;
      if (next >= last) { onStep(null); setPlaying(false); } else onStep(next);
    }, 900);
    return () => clearTimeout(t);
  }, [playing, current, last, onStep]);

  if (edges.length < 2) return null;
  const at = edges[current]?.ts;

  const toggle = () => {
    if (playing) { setPlaying(false); return; }
    if (current >= last) onStep(0);
    setPlaying(true);
  };

  return (
    <div className="no-print rounded-lg border border-line bg-canvas p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="secondary" onClick={() => { setPlaying(false); onStep(Math.max(0, current - 1)); }}
                disabled={current <= 0} aria-label="Previous payment">
          <Icon name="back" className="h-4 w-4" />
        </Button>
        <Button size="sm" variant="navy" onClick={toggle} aria-label={playing ? "Pause replay" : "Play replay"} className="min-w-24">
          <Icon name={playing ? "pause" : "play"} className="h-4 w-4" />{playing ? "Pause" : "Replay"}
        </Button>
        <Button size="sm" variant="secondary" onClick={() => { setPlaying(false); onStep(current + 1 >= last ? null : current + 1); }}
                disabled={current >= last} aria-label="Next payment">
          <Icon name="forward" className="h-4 w-4" />
        </Button>
        <div className="ml-auto text-right text-xs text-muted" aria-live="polite">
          <span className="font-semibold text-ink">Payment {current + 1} of {edges.length}</span>
          {at && <> · {time(at)}</>}
        </div>
      </div>
      <label className="mt-2 block">
        <span className="sr-only">Replay position</span>
        <input type="range" className="w-full" min={0} max={last} value={current}
               aria-valuetext={`Payment ${current + 1} of ${edges.length}${at ? `, ${time(at)}` : ""}`}
               onChange={(e) => { setPlaying(false); const v = Number(e.target.value); onStep(v >= last ? null : v); }} />
      </label>
    </div>
  );
}
