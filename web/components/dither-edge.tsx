const COLS = 48;
const ROWS = 6;

/**
 * The pixel-dither staircase between a dark section and a light one. `to` is the colour below the edge.
 * Each row fills more of its squares, so the colour change reads as a stepped dissolve.
 */
export function DitherEdge({ to }: { to: "paper" | "ink" }) {
  const fill = to === "paper" ? "var(--color-paper)" : "var(--color-ink)";
  const background = to === "paper" ? "bg-ink" : "bg-paper";
  const cells: { x: number; y: number }[] = [];
  for (let y = 0; y < ROWS; y++) {
    for (let x = 0; x < COLS; x++) {
      // A fixed pattern (no randomness), so the server and the browser draw the same edge.
      const threshold = ((x * 7 + y * 13) % 11) / 11;
      if (threshold < (y + 1) / ROWS) cells.push({ x, y });
    }
  }
  return (
    <div aria-hidden className={`relative z-10 ${background}`}>
      <svg
        viewBox={`0 0 ${COLS} ${ROWS}`}
        preserveAspectRatio="none"
        className="block h-10 w-full md:h-16"
        shapeRendering="crispEdges"
      >
        {cells.map(({ x, y }) => (
          <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={fill} />
        ))}
      </svg>
    </div>
  );
}
