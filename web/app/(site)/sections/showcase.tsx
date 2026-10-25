import { LaptopFrame } from "@/components/laptop-frame";
import { PixelHeading } from "@/components/pixel-heading";
import { formatInr, formatIst } from "@/lib/format";
import type { TrailAccount } from "@/lib/gateway/types";
import { DEMO_TRAIL } from "@/lib/showcase";

const INSTITUTIONS: Record<string, string> = {
  "bank-a": "Bank A",
  "bank-b": "Bank B",
  "bank-c": "Bank C",
  "bank-d": "Bank D",
  "wallet-w": "Wallet W",
  "exchange-x": "Exchange X",
};

function outcome(a: TrailAccount): string {
  const cashed = a.exits.reduce((sum, e) => sum + e.traced_amount, 0);
  if (cashed > 0) return `${formatInr(cashed)} cashed out at ${a.exits.length} ATMs`;
  if (a.held > 0) return "Lien placed";
  return "Passed on";
}

function Card({ account }: { account: TrailAccount }) {
  return (
    <div className="border border-grey-900 bg-[#171717] p-[0.9em]">
      <p className="text-[0.75em] text-grey-500">{INSTITUTIONS[account.member ?? ""] ?? "Off network"}</p>
      <p className="mt-[0.2em] truncate text-[0.95em] text-white">{account.holder_name}</p>
      <p className="mt-[0.6em] text-[0.75em] text-grey-500">Victim money in</p>
      <p className="font-mono text-[0.9em] tabular-nums">{formatInr(account.traced_in)}</p>
      <div className="mt-[0.6em] flex items-center justify-between gap-[0.5em]">
        <span className="text-[0.75em] text-grey-300">{outcome(account)}</span>
        {account.held > 0 && (
          <span className="bg-cyan px-[0.4em] font-mono text-[0.8em] text-ink tabular-nums">
            {formatInr(account.held)}
          </span>
        )}
      </div>
    </div>
  );
}

export function Showcase() {
  const t = DEMO_TRAIL;
  const lastEvent = t.accounts
    .flatMap((a) => [a.credit.at, ...a.exits.map((e) => e.at)])
    .reduce((a, b) => (a > b ? a : b));
  const layers = [...new Set(t.accounts.map((a) => a.layer))].sort((a, b) => a - b);
  const totals = [
    ["Reported", t.reported],
    ["Held", t.held],
    ["Cashed out", t.cashed_out],
    ["Off network", t.off_network],
    ["Waiting", t.waiting],
  ] as const;
  return (
    <section aria-labelledby="showcase-title" className="relative z-10 px-5 py-28 md:py-40">
      <div className="mx-auto max-w-6xl text-center">
        <PixelHeading text="The whole trail, in one view" className="text-3xl md:text-4xl" />
        <p
          id="showcase-title"
          className="mx-auto mt-5 max-w-[50ch] text-[15px] leading-relaxed text-grey-300"
        >
          The investigating officer sees every account the money reached, what each bank holds, and what left
          the system, with totals that always add up to the amount reported.
        </p>
      </div>
      <div className="mt-16">
        <LaptopFrame label="The Ripple workspace showing a case trail across six institutions">
          <div className="@container h-full">
            <div className="flex h-full text-left text-[1.15cqw] text-grey-300">
              <aside className="flex w-[14em] shrink-0 flex-col gap-[0.9em] border-r border-grey-900 p-[1.2em]">
                <span className="pixel text-[1.3em] text-white">Ripple</span>
                <span className="mt-[1em] text-[0.85em] text-white">Cases</span>
                <span className="text-[0.85em]">Simulation</span>
              </aside>
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex items-center justify-between border-b border-grey-900 px-[1.4em] py-[0.8em] text-[0.8em]">
                  <span>CFCFRMS · Police officer</span>
                  <span className="font-mono">{formatIst(lastEvent)}</span>
                </div>
                <div className="flex-1 overflow-hidden p-[1.4em]">
                  <p className="text-[0.8em] text-grey-500">Case</p>
                  <p className="font-mono text-[1.1em] text-white">{t.ack_number}</p>
                  <div className="mt-[1em] grid grid-cols-5 gap-px bg-grey-900">
                    {totals.map(([label, value]) => (
                      <div key={label} className="bg-ink p-[0.7em]">
                        <p className="text-[0.7em] text-grey-500">{label}</p>
                        <p
                          className={`font-mono text-[0.95em] tabular-nums ${label === "Held" ? "text-cyan" : "text-white"}`}
                        >
                          {formatInr(value)}
                        </p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-[1.2em] grid grid-cols-3 gap-[1em]">
                    {layers.map((layer) => (
                      <div key={layer} className="flex flex-col gap-[0.7em]">
                        <p className="text-[0.7em] text-grey-500">Layer {layer}</p>
                        {t.accounts
                          .filter((a) => a.layer === layer)
                          .map((a) => (
                            <Card key={a.notice_id} account={a} />
                          ))}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </LaptopFrame>
      </div>
    </section>
  );
}
