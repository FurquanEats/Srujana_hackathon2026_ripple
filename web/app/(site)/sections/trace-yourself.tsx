"use client";

import { useId, useState } from "react";

import { formatInr } from "@/lib/format";

/** M3's account in the demo story, in paise: its own money, then the victim's money arriving on top. */
const OWN = 300_000_00;
const VICTIM = 250_000_00;
const STEP = 5_000_00;

/**
 * The SOP's victims-first rule, live: a payment out of the account carries the victim's money before the holder's
 * own (MHA SOP for NCRP-CFCFRMS, Annexure V). Whatever victim money is left is what the lien covers.
 */
export function traceSpend(spent: number) {
  const fromVictim = Math.min(spent, VICTIM);
  const fromOwn = Math.min(Math.max(spent - VICTIM, 0), OWN);
  return { lien: VICTIM - fromVictim, ownLeft: OWN - fromOwn, passedOn: fromVictim };
}

export function TraceYourself() {
  const id = useId();
  const [spent, setSpent] = useState(120_000_00);
  const { lien, ownLeft, passedOn } = traceSpend(spent);
  const total = OWN + VICTIM;
  const bar = (part: number) => `${(part / total) * 100}%`;
  return (
    <section aria-labelledby={`${id}-title`} className="relative z-10 px-5 py-28 md:py-40">
      <div className="mx-auto max-w-xl text-center">
        <h2 id={`${id}-title`} className="pixel text-[24px] md:text-[30px]">
          Trace it yourself
        </h2>
        <p className="mx-auto mt-5 max-w-[46ch] text-[14px] leading-relaxed text-muted">
          A shop holds {formatInr(OWN)} of its own money when {formatInr(VICTIM)} of a victim&apos;s money
          arrives. Move the slider to choose how much the shop pays out before the notice reaches its bank.
        </p>
      </div>
      <div className="mx-auto mt-14 max-w-xl border border-line bg-surface p-6 text-left md:p-8">
        <label
          htmlFor={`${id}-spent`}
          className="flex items-baseline justify-between gap-4 text-[13px] text-muted"
        >
          <span>Paid out by the shop</span>
          <output htmlFor={`${id}-spent`} className="font-mono text-[15px] tabular-nums">
            {formatInr(spent)}
          </output>
        </label>
        <input
          id={`${id}-spent`}
          type="range"
          min={0}
          max={total}
          step={STEP}
          value={spent}
          onChange={(e) => setSpent(Number(e.target.value))}
          className="mt-4 w-full accent-[var(--color-accent)]"
        />
        <div aria-hidden className="mt-8 flex h-6 w-full overflow-hidden bg-grey-900">
          <span className="block h-full bg-accent transition-[width]" style={{ width: bar(lien) }} />
          <span className="block h-full bg-grey-500 transition-[width]" style={{ width: bar(ownLeft) }} />
        </div>
        <dl className="mt-6 grid grid-cols-3 gap-4 text-[13px]">
          <div>
            <dt className="text-muted">Lien on the victim&apos;s money</dt>
            <dd className="mt-1 font-mono text-[15px] text-accent tabular-nums">{formatInr(lien)}</dd>
          </div>
          <div>
            <dt className="text-muted">Shop&apos;s own money, free</dt>
            <dd className="mt-1 font-mono text-[15px] tabular-nums">{formatInr(ownLeft)}</dd>
          </div>
          <div>
            <dt className="text-muted">Passed on, traced to the next bank</dt>
            <dd className="mt-1 font-mono text-[15px] tabular-nums">{formatInr(passedOn)}</dd>
          </div>
        </dl>
        <p className="mt-6 text-[12px] leading-relaxed text-faint">
          Payments out take the victim&apos;s money first, as in the SOP&apos;s own worked examples. The lien
          never touches the shop&apos;s own money, and the next bank receives a notice for whatever was passed
          on.
        </p>
      </div>
    </section>
  );
}
