import { formatInr } from "@/lib/format";

export type FlowNode = {
  label: string;
  sub?: string;
  amount: number;
  /** victim: traced victim money (green); exit: left the banking system; own: the holder's own money */
  kind?: "victim" | "exit" | "own" | "plain" | "held";
  href?: string;
};

const W = 920;
const NODE_W = 230;
const ROW = 64;
const GAP = 12;
const MIN_STROKE = 3;
const MAX_STROKE = 34;

const COLOURS: Record<NonNullable<FlowNode["kind"]>, string> = {
  victim: "var(--color-accent)",
  held: "var(--color-accent)",
  exit: "#d14343",
  own: "var(--faint)",
  plain: "var(--muted)",
};

function Box({ node, x, y, align }: { node: FlowNode; x: number; y: number; align: "left" | "right" }) {
  const colour = COLOURS[node.kind ?? "plain"];
  const body = (
    <g transform={`translate(${x},${y})`}>
      <rect width={NODE_W} height={ROW - GAP} fill="var(--surface)" stroke="var(--line)" />
      <rect x={align === "left" ? NODE_W - 4 : 0} width={4} height={ROW - GAP} fill={colour} />
      <text x={12} y={20} fontSize={13} fill="var(--fg)">
        {node.label.length > 30 ? `${node.label.slice(0, 29)}…` : node.label}
      </text>
      <text x={12} y={38} fontSize={12} fill="var(--muted)" fontFamily="var(--font-mono)">
        {`${formatInr(node.amount)}${node.sub ? ` · ${node.sub}` : ""}`.slice(0, 36)}
      </text>
    </g>
  );
  return node.href ? (
    <a href={node.href} className="cursor-pointer [&:hover_rect:first-child]:stroke-[var(--fg)]">
      {body}
    </a>
  ) : (
    body
  );
}

/**
 * Money into and out of one account as ribbons whose width follows the amount: where it came from on the left,
 * where it went on the right. Victim money is green, money that left the banking system is red.
 */
export function FlowGraph({
  title,
  centre,
  inflows,
  outflows,
  caption,
}: {
  title: string;
  centre: { label: string; sub?: string };
  inflows: FlowNode[];
  outflows: FlowNode[];
  caption?: string;
}) {
  const rows = Math.max(inflows.length, outflows.length, 1);
  const H = rows * ROW + 20;
  const max = Math.max(...inflows.map((n) => n.amount), ...outflows.map((n) => n.amount), 1);
  const stroke = (amount: number) => MIN_STROKE + (MAX_STROKE - MIN_STROKE) * Math.sqrt(amount / max);
  const cx = W / 2 - 90;
  const cw = 180;
  const cy = H / 2 - 40;
  const yFor = (i: number, n: number) => (H - n * ROW) / 2 + i * ROW + 10;
  return (
    <figure className="border-line mb-8 border p-4">
      <figcaption className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-fg text-[15px] font-semibold">{title}</span>
        <span className="text-faint flex gap-4 text-xs">
          <span>
            <span aria-hidden className="mr-1 inline-block size-2 bg-accent" />
            Victim money
          </span>
          <span>
            <span aria-hidden className="mr-1 inline-block size-2 bg-[#d14343]" />
            Left the banks
          </span>
          <span>
            <span aria-hidden className="mr-1 inline-block size-2 bg-[var(--faint)]" />
            Holder&apos;s own
          </span>
        </span>
      </figcaption>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full min-w-[640px]" role="img" aria-label={title}>
          {inflows.map((n, i) => {
            const y = yFor(i, inflows.length) + (ROW - GAP) / 2;
            return (
              <path
                key={`in-${i}`}
                d={`M${NODE_W},${y} C${(NODE_W + cx) / 2},${y} ${(NODE_W + cx) / 2},${cy + 40} ${cx},${cy + 40}`}
                fill="none"
                stroke={COLOURS[n.kind ?? "plain"]}
                strokeOpacity={0.45}
                strokeWidth={stroke(n.amount)}
              />
            );
          })}
          {outflows.map((n, i) => {
            const y = yFor(i, outflows.length) + (ROW - GAP) / 2;
            const x2 = W - NODE_W;
            return (
              <path
                key={`out-${i}`}
                d={`M${cx + cw},${cy + 40} C${(cx + cw + x2) / 2},${cy + 40} ${(cx + cw + x2) / 2},${y} ${x2},${y}`}
                fill="none"
                stroke={COLOURS[n.kind ?? "plain"]}
                strokeOpacity={0.45}
                strokeWidth={stroke(n.amount)}
              />
            );
          })}
          <g transform={`translate(${cx},${cy})`}>
            <rect width={cw} height={80} fill="var(--fg)" />
            <text x={cw / 2} y={34} textAnchor="middle" fontSize={14} fill="var(--surface)" fontWeight={600}>
              {centre.label.length > 22 ? `${centre.label.slice(0, 21)}…` : centre.label}
            </text>
            {centre.sub && (
              <text x={cw / 2} y={56} textAnchor="middle" fontSize={12} fill="var(--surface)" opacity={0.75}>
                {centre.sub}
              </text>
            )}
          </g>
          {inflows.map((n, i) => (
            <Box key={`bin-${i}`} node={n} x={0} y={yFor(i, inflows.length)} align="left" />
          ))}
          {outflows.map((n, i) => (
            <Box key={`bout-${i}`} node={n} x={W - NODE_W} y={yFor(i, outflows.length)} align="right" />
          ))}
          {inflows.length === 0 && (
            <text x={NODE_W / 2} y={H / 2} textAnchor="middle" fontSize={12} fill="var(--faint)">
              No credits in this view
            </text>
          )}
          {outflows.length === 0 && (
            <text x={W - NODE_W / 2} y={H / 2} textAnchor="middle" fontSize={12} fill="var(--faint)">
              Nothing left the account
            </text>
          )}
        </svg>
      </div>
      {caption && <p className="text-faint mt-2 text-xs">{caption}</p>}
    </figure>
  );
}
