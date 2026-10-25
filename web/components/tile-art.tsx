/**
 * The trail as tiles: each institution is a dark ridged tile and the victim's money is cyan pixels. Money that is
 * held under a lien sits inside a cyan outline; money cashed out at an ATM is grey. This static drawing is the hero
 * art and the fallback for the 3D scene.
 */

type Tile = {
  id: string;
  label: string;
  x: number;
  y: number;
  rotate: number;
  pixels: number; // victim money, in pixels
  state: "source" | "held" | "passed" | "cashed";
};

const TILES: Tile[] = [
  { id: "a", label: "Bank A", x: 30, y: 150, rotate: -4, pixels: 0, state: "source" },
  { id: "b", label: "Bank B", x: 215, y: 60, rotate: 3, pixels: 10, state: "held" },
  { id: "c", label: "Bank C", x: 215, y: 255, rotate: -2, pixels: 0, state: "passed" },
  { id: "w", label: "Wallet W", x: 405, y: 20, rotate: -3, pixels: 15, state: "held" },
  { id: "x", label: "Exchange X", x: 420, y: 190, rotate: 4, pixels: 10, state: "held" },
  { id: "atm", label: "ATM", x: 405, y: 350, rotate: -5, pixels: 20, state: "cashed" },
];

const SIZE = 150;
const PIXEL = 9;

function pixelCells(count: number, seed: number) {
  const cells: { cx: number; cy: number }[] = [];
  let n = seed;
  for (let i = 0; cells.length < count && i < 200; i++) {
    n = (n * 9301 + 49297) % 233280;
    const col = n % 6;
    const row = Math.floor(n / 6) % 8;
    if (!cells.some((c) => c.cx === col && c.cy === row)) cells.push({ cx: col, cy: row });
  }
  return cells;
}

const PATHS = [
  "M180 225 C 200 180, 215 160, 240 140",
  "M180 225 C 200 260, 210 290, 240 320",
  "M365 120 C 385 110, 400 100, 425 95",
  "M365 330 C 390 300, 400 280, 440 265",
  "M365 330 C 385 360, 395 390, 430 420",
];

export function TileArt({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 600 520"
      role="img"
      aria-labelledby="tile-art-title"
      className={className}
      shapeRendering="geometricPrecision"
    >
      <title id="tile-art-title">
        A victim&apos;s money leaves Bank A and splits across Bank B, Bank C, Wallet W, Exchange X and an ATM.
        Liens hold the traced money at Bank B, Wallet W and Exchange X; the ATM cash has left the system.
      </title>
      <defs>
        <pattern id="ridges" width="6" height="6" patternUnits="userSpaceOnUse">
          <rect width="6" height="6" fill="#1b1b1b" />
          <rect width="1" height="6" fill="#262626" />
        </pattern>
        <filter id="tile-shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="14" stdDeviation="14" floodColor="#000" floodOpacity="0.55" />
        </filter>
      </defs>

      {PATHS.map((d) => (
        <path
          key={d}
          d={d}
          fill="none"
          stroke="#00a9cc"
          strokeOpacity="0.45"
          strokeWidth="1.5"
          strokeDasharray="3 5"
        />
      ))}

      {TILES.map((t, i) => {
        const cells = pixelCells(t.pixels, i * 17 + 5);
        const colour = t.state === "cashed" ? "#6b6b6b" : "#00a9cc";
        return (
          <g
            key={t.id}
            transform={`translate(${t.x} ${t.y}) rotate(${t.rotate} ${SIZE / 2} ${SIZE / 2})`}
            filter="url(#tile-shadow)"
          >
            <rect width={SIZE} height={SIZE} rx="12" fill="url(#ridges)" stroke="#2f2f2f" />
            {t.state === "held" && (
              <rect x="-4" y="-4" width={SIZE + 8} height={SIZE + 8} rx="15" fill="none" stroke="#00a9cc" />
            )}
            <text
              x="14"
              y="26"
              fill="#b3b3b3"
              fontFamily="var(--font-pixel)"
              fontSize="13"
              letterSpacing="-0.5"
            >
              {t.label.toUpperCase()}
            </text>
            {t.state === "source" && (
              <text x="14" y={SIZE - 16} fill="#6b6b6b" fontFamily="var(--font-pixel)" fontSize="11">
                VICTIM
              </text>
            )}
            {cells.map(({ cx, cy }) => (
              <rect
                key={`${cx}-${cy}`}
                x={SIZE - 14 - 6 * (PIXEL + 2) + cx * (PIXEL + 2)}
                y={40 + cy * (PIXEL + 2)}
                width={PIXEL}
                height={PIXEL}
                fill={colour}
              />
            ))}
          </g>
        );
      })}
    </svg>
  );
}
