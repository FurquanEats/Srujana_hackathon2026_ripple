/** Money and time the way the workspace shows them: Indian digit grouping, and IST with the date. */

const PAISE_PER_RUPEE = 100n;

function groupIndian(digits: string): string {
  if (digits.length <= 3) return digits;
  const last3 = digits.slice(-3);
  const rest = digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${rest},${last3}`;
}

/**
 * Format whole paise as rupees: 2500000000 -> "₹2,50,00,000". Paise are shown only when there are any.
 * `symbol` is "₹" for body text and "Rs" for the pixel face, which has no rupee sign.
 */
export function formatInr(paise: number | bigint, symbol: "₹" | "Rs" = "₹"): string {
  const value = BigInt(paise);
  const sign = value < 0n ? "-" : "";
  const abs = value < 0n ? -value : value;
  const rupees = groupIndian((abs / PAISE_PER_RUPEE).toString());
  const fraction = abs % PAISE_PER_RUPEE;
  const tail = fraction === 0n ? "" : `.${fraction.toString().padStart(2, "0")}`;
  const prefix = symbol === "Rs" ? "Rs " : "₹";
  return `${sign}${prefix}${rupees}${tail}`;
}

const IST = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** An ISO 8601 time as "25 Oct 2026, 22:05 IST". */
export function formatIst(iso: string): string {
  const parts = Object.fromEntries(IST.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${parts.day} ${parts.month} ${parts.year}, ${parts.hour}:${parts.minute} IST`;
}
