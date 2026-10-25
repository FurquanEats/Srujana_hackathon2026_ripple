import { LaptopFrame } from "@/components/laptop-frame";
import { Pinned } from "@/components/pinned";
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
      <p className="text-[0.75em] text-[#8f8f8f]">{INSTITUTIONS[account.member ?? ""] ?? "Off network"}</p>
      <p className="mt-[0.2em] truncate text-[0.95em] text-white">{account.holder_name}</p>
      <p className="mt-[0.6em] text-[0.75em] text-[#8f8f8f]">Victim money in</p>
      <p className="font-mono text-[0.9em] tabular-nums">{formatInr(account.traced_in)}</p>
      <div className="mt-[0.6em] flex items-center justify-between gap-[0.5em]">
        <span className="text-[0.75em] text-grey-300">{outcome(account)}</span>
        {account.held > 0 && (
          <span className="bg-accent px-[0.4em] font-mono text-[0.8em] text-ink tabular-nums">
            {formatInr(account.held)}
          </span>
        )}
      </div>
    </div>
  );
}

const CAPTIONS = [
  {
    title: "The whole trail, in one view",
    body: "The investigating officer sees every account the money reached, what each bank holds, and what left the system.",
  },
  {
    title: "Totals that always add up",
    body: "Held, cashed out, off network and waiting always add up to the amount the victim reported, to the rupee.",
  },
  {
    title: "Exits, named for the police",
    body: "Cash withdrawals come with the ATM ID and place, so the police can follow the money that left the banks.",
  },
] as const;

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
    <section aria-label="The workspace" className="relative z-10">
      <Pinned captions={CAPTIONS}>
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
                  <p className="text-[0.8em] text-[#8f8f8f]">Case</p>
                  <p className="font-mono text-[1.1em] text-white">{t.ack_number}</p>
                  <div className="mt-[1em] grid grid-cols-5 gap-px bg-grey-900">
                    {totals.map(([label, value]) => (
                      <div key={label} className="bg-ink p-[0.7em]">
                        <p className="text-[0.7em] text-[#8f8f8f]">{label}</p>
                        <p
                          className={`font-mono text-[0.95em] tabular-nums ${label === "Held" ? "text-accent" : "text-white"}`}
                        >
                          {formatInr(value)}
                        </p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-[1.2em] grid grid-cols-3 gap-[1em]">
                    {layers.map((layer) => (
                      <div key={layer} className="flex flex-col gap-[0.7em]">
                        <p className="text-[0.7em] text-[#8f8f8f]">Layer {layer}</p>
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
      </Pinned>
    </section>
  );
}
