import { formatIst } from "@/lib/format";
import type { Hold } from "@/lib/gateway/types";

const DAY = 86_400_000;
const SPAN_DAYS = 60;

/**
 * The hold's 60 days on one line: the customer's 20 days to explain, the bank's decision by day 30 (or 10 days
 * after an explanation), and the 60-day cap, with the network's current time marked.
 */
export function HoldTimeline({ hold, now }: { hold: Hold; now: string }) {
  const start = new Date(hold.placed_at).getTime();
  const at = (iso: string) =>
    Math.max(0, Math.min(100, ((new Date(iso).getTime() - start) / (SPAN_DAYS * DAY)) * 100));
  const today = at(now);
  const marks = hold.deadlines.filter((d) => d.name !== "Customer notified");
  return (
    <figure className="w-full">
      <div className="relative mt-8 mb-2 h-2 bg-[var(--line)]">
        <div
          className="absolute inset-y-0 left-0 bg-accent"
          style={{ width: `${hold.released_at ? at(hold.released_at) : today}%` }}
        />
        {marks.map((d) => (
          <span
            key={d.name}
            className={`absolute -top-1.5 h-5 w-px ${d.state === "met" ? "bg-[var(--muted)]" : d.state === "open" ? "bg-[var(--fg)]" : "bg-red-500"}`}
            style={{ left: `${at(d.due)}%` }}
            aria-hidden
          />
        ))}
        <span
          className="text-faint absolute -top-7 -translate-x-1/2 text-[11px] whitespace-nowrap"
          style={{ left: `${Math.min(92, Math.max(8, today))}%` }}
        >
          Now
        </span>
      </div>
      <div className="text-faint relative h-4 text-[11px]">
        {[0, 20, 30, 60].map((day) => (
          <span
            key={day}
            className={`absolute ${day === 0 ? "" : day === 60 ? "-translate-x-full" : "-translate-x-1/2"}`}
            style={{ left: `${(day / SPAN_DAYS) * 100}%` }}
          >
            Day {day}
          </span>
        ))}
      </div>
      <figcaption className="sr-only">Timeline of the hold&apos;s deadlines</figcaption>
      <ol className="mt-5 grid gap-2">
        {hold.deadlines.map((d) => (
          <li
            key={d.name}
            className="border-line grid gap-1 border-b pb-2 text-[13px] sm:grid-cols-[180px_1fr_auto] sm:gap-4"
          >
            <span className="text-fg">{d.name}</span>
            <span className="text-muted text-xs">{d.rule}</span>
            <span
              className={`text-xs whitespace-nowrap ${d.state === "met" ? "text-faint" : d.state === "open" ? "text-fg" : "text-red-500"}`}
            >
              {d.state === "met"
                ? `Met ${formatIst(d.met_at ?? d.due)}`
                : `${d.state === "open" ? "Due" : "Missed"} ${formatIst(d.due)}`}
            </span>
          </li>
        ))}
      </ol>
    </figure>
  );
}
