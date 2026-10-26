"use client";

import { useEffect, useMemo, useState } from "react";

import { EXIT, RAIL } from "@/lib/accounts";
import { formatInr, formatIst, formatIstSeconds } from "@/lib/format";
import type { Trail } from "@/lib/gateway/types";
import { layout, moments, NODE_H, NODE_W, totalsAt } from "@/lib/trail";

/**
 * The trail as a graph, one column per layer, with a slider that replays the money hop by hop: an account appears
 * when the victim's money reaches it, and cash-outs appear when they happen.
 */
export function TrailReplay({ trail, institutions }: { trail: Trail; institutions: Record<string, string> }) {
  const { nodes, width, height } = useMemo(() => layout(trail), [trail]);
  const steps = useMemo(() => moments(trail), [trail]);
  const [index, setIndex] = useState(steps.length - 1);
  const [playing, setPlaying] = useState(false);
  const at = steps[index] ?? "";
  const totals = totalsAt(trail, at);
  const byId = new Map(nodes.map((n) => [n.account.notice_id, n]));

  useEffect(() => {
    if (!playing) return;
    const timer = setTimeout(() => {
      if (index >= steps.length - 1) setPlaying(false);
      else setIndex((i) => i + 1);
    }, 700);
    return () => clearTimeout(timer);
  }, [playing, index, steps.length]);

  const pad = 8;
  return (
    <section aria-labelledby="graph">
      <h2 id="graph" className="pixel mb-4 text-lg">
        Replay
      </h2>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          className="button button-ghost"
          onClick={() => {
            if (index >= steps.length - 1) setIndex(0);
            setPlaying((p) => !p);
          }}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, steps.length - 1)}
          value={index}
          onChange={(e) => {
            setPlaying(false);
            setIndex(Number(e.target.value));
          }}
          aria-label="Replay position"
          aria-valuetext={at ? formatIst(at) : ""}
          className="min-w-40 flex-1 accent-[var(--color-accent)]"
        />
        <span className="text-muted font-mono text-xs tabular-nums">{at ? formatIst(at) : ""}</span>
      </div>
      <p className="text-muted mb-4 text-[13px]" aria-live="polite">
        Step {index + 1} of {steps.length}: the money has reached {totals.accounts} of {trail.accounts.length}{" "}
        accounts, and {formatInr(totals.cashedOut)} has been cashed out so far.
      </p>
      <div className="border-line overflow-x-auto border p-3">
        <svg
          viewBox={`${-pad} ${-pad} ${width + pad * 2} ${height + pad * 2}`}
          width={width + pad * 2}
          height={height + pad * 2}
          role="img"
          aria-label={`Money trail with ${trail.accounts.length} accounts`}
          className="block max-w-none"
        >
          {nodes.map(({ account, x, y }) => {
            const parent = account.parent_id ? byId.get(account.parent_id) : undefined;
            if (!parent) return null;
            const shown = account.credit.at <= at;
            const x1 = parent.x + NODE_W;
            const y1 = parent.y + NODE_H / 2;
            const y2 = y + NODE_H / 2;
            const mid = (x1 + x) / 2;
            return (
              <g
                key={`e-${account.notice_id}`}
                opacity={shown ? 1 : 0.12}
                className="transition-opacity duration-500"
              >
                <path
                  d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x},${y2}`}
                  fill="none"
                  stroke="var(--muted)"
                  strokeWidth={1}
                />
              </g>
            );
          })}
          {nodes.map(({ account, x, y }) => {
            const shown = account.credit.at <= at;
            const cashed = account.exits.filter((e) => e.at <= at).reduce((s, e) => s + e.traced_amount, 0);
            const held = account.held > 0 && at >= steps[steps.length - 1]!;
            return (
              <g
                key={account.notice_id}
                transform={`translate(${x},${y})`}
                opacity={shown ? 1 : 0.15}
                className="transition-opacity duration-500"
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  fill="var(--panel)"
                  stroke={held ? "var(--color-accent)" : "var(--line)"}
                  strokeWidth={held ? 2 : 1}
                />
                <text x={10} y={18} fontSize={10.5} fill="var(--faint)">
                  {`Layer ${account.layer} · ${institutions[account.member ?? ""] ?? "Off network"}`}
                </text>
                <text x={10} y={36} fontSize={13} fill="var(--fg)">
                  {(account.holder_name ?? "Unknown holder").length > 33
                    ? `${(account.holder_name ?? "").slice(0, 32)}…`
                    : (account.holder_name ?? "Unknown holder")}
                </text>
                <text x={10} y={54} fontSize={11.5} fill="var(--muted)" fontFamily="var(--font-mono)">
                  {`In ${formatInr(account.traced_in)} · ${RAIL[account.credit.rail] ?? account.credit.rail} · ${formatIstSeconds(account.credit.at).slice(-8)}`}
                </text>
                {held ? (
                  <g>
                    <rect x={10} y={60} width={120} height={14} fill="var(--color-accent)" />
                    <text x={14} y={71} fontSize={10.5} fill="#121212" fontFamily="var(--font-mono)">
                      {`Held ${formatInr(account.held)}`}
                    </text>
                  </g>
                ) : cashed > 0 ? (
                  <text x={10} y={71} fontSize={10.5} fill="var(--fg)">
                    {`Cashed out ${formatInr(cashed)}`}
                  </text>
                ) : account.state !== "answered" ? (
                  <text x={10} y={71} fontSize={10.5} fill="var(--faint)">
                    {account.state === "waiting"
                      ? "Waiting for the bank"
                      : account.state === "off_network"
                        ? "Left the network"
                        : "Not found"}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>

      <h3 className="pixel mt-8 mb-3 text-base">Timeline (IST)</h3>
      <ol className="grid gap-1.5">
        {trail.accounts
          .flatMap((a) => [
            {
              at: a.credit.at,
              text: `${formatInr(a.traced_in)} reached ${a.holder_name ?? "an account"} (layer ${a.layer}, ${institutions[a.member ?? ""] ?? "off network"}) by ${RAIL[a.credit.rail] ?? a.credit.rail}`,
              exit: false,
            },
            ...a.exits.map((e) => ({
              at: e.at,
              text: `${formatInr(e.traced_amount)} left the banks: ${EXIT[e.mode]} at ${e.identifier}${e.location ? `, ${e.location}` : ""}`,
              exit: true,
            })),
          ])
          .sort((x, y) => x.at.localeCompare(y.at))
          .map((e, i) => (
            <li
              key={`${e.at}-${i}`}
              className={`grid grid-cols-[150px_minmax(0,1fr)] gap-3 text-[13px] ${e.at <= at ? "" : "opacity-40"}`}
            >
              <span className="font-mono text-xs tabular-nums">{formatIstSeconds(e.at)}</span>
              <span className="break-words">
                <span
                  aria-hidden
                  className={`mr-2 inline-block size-2 ${e.exit ? "bg-red-500" : "bg-accent"}`}
                />
                {e.text}
              </span>
            </li>
          ))}
      </ol>

      <h3 id="exits" className="pixel mt-10 mb-3 scroll-mt-6 text-base">
        Exits for the police
      </h3>
      {trail.accounts.flatMap((a) => a.exits).length === 0 ? (
        <p className="text-faint text-sm">No money left the banking system on this trail.</p>
      ) : (
        <ul className="grid gap-2 md:grid-cols-2">
          {trail.accounts.flatMap((a) =>
            a.exits.map((e) => (
              <li
                key={e.reference}
                className={`border-line min-w-0 border p-3 text-sm break-words ${e.at <= at ? "" : "opacity-40"}`}
              >
                {EXIT[e.mode]} of {formatInr(e.traced_amount)} at{" "}
                <span className="font-mono">{e.identifier}</span>
                {e.location ? `, ${e.location}` : ""}
                <span className="text-muted block text-xs">
                  {a.holder_name} at {institutions[a.member ?? ""] ?? "an off-network institution"},{" "}
                  {formatIst(e.at)}
                </span>
              </li>
            )),
          )}
        </ul>
      )}
    </section>
  );
}
