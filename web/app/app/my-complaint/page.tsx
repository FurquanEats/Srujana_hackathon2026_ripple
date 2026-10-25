import type { Metadata } from "next";

import { Held, Money, PageHeader } from "@/components/workspace/ui";
import { formatInr, formatIst } from "@/lib/format";
import { myComplaint } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

export const metadata: Metadata = { title: "My complaint" };

const FIFTY_THOUSAND = 50_000_00;

export default async function MyComplaintPage() {
  const session = await requireRole("victim");
  const c = await myComplaint(session);
  const held = c.places.filter((p) => p.held > 0);
  const cashed = c.places.filter((p) => p.cashed_out > 0);
  return (
    <>
      <PageHeader
        title="Your complaint"
        lead={`Acknowledgement ${c.ack_number}${c.filed_at ? `, filed ${formatIst(c.filed_at)}` : ""}. This is what has happened to the money you reported, as the banks answered.`}
      />
      <div className="mb-10 grid gap-3 sm:grid-cols-3">
        <div className="border-line border p-5">
          <p className="text-faint text-xs">You reported</p>
          <p className="mt-1 text-2xl">
            <Money paise={c.reported} />
          </p>
        </div>
        <div className="border-accent border p-5">
          <p className="text-faint text-xs">Held for you</p>
          <p className="mt-1 text-2xl">
            <Held paise={c.held} />
          </p>
          <p className="text-faint mt-1 text-xs">Frozen in the accounts it reached, so nobody can spend it</p>
        </div>
        <div className="border-line border p-5">
          <p className="text-faint text-xs">Taken out before the hold</p>
          <p className="mt-1 text-2xl">
            <Money paise={c.cashed_out} />
          </p>
        </div>
      </div>

      <section className="mb-10">
        <h2 className="pixel mb-4 text-lg">Where your money is held</h2>
        {held.length === 0 ? (
          <p className="text-muted text-sm">
            None of it could be held: it had left the banks before the complaint reached them.
          </p>
        ) : (
          <ul className="grid gap-2">
            {held.map((p, i) => (
              <li
                key={`${p.member}-${i}`}
                className="border-line flex flex-wrap items-baseline justify-between gap-3 border p-4"
              >
                <span className="text-[15px]">
                  {p.institution}
                  <span className="text-faint block text-xs">
                    {p.layer === 1
                      ? "The account you paid"
                      : `${p.layer - 1} transfer${p.layer > 2 ? "s" : ""} after the account you paid`}
                  </span>
                </span>
                <Held paise={p.held} />
              </li>
            ))}
          </ul>
        )}
        {cashed.length > 0 && (
          <p className="text-muted mt-4 text-sm">
            {formatInr(c.cashed_out)} was withdrawn as cash or moved out of the banking system before the
            hold. The police have the ATM and exchange details to follow it.
          </p>
        )}
      </section>

      <section className="mb-10 max-w-3xl">
        <h2 className="pixel mb-4 text-lg">How you can get it back</h2>
        <ol className="grid list-decimal gap-3 pl-5 text-[15px] leading-relaxed">
          <li>
            The held money stays frozen until the police or a court decides who it belongs to. Banks cannot
            hand it back on their own.
          </li>
          <li>
            The police can return held money to you as interim custody under section 106(3) of the BNSS.{" "}
            {c.held > 0 && c.held < FIFTY_THOUSAND
              ? "Your held amount is below ₹50,000, so this can be done without an FIR."
              : "Above ₹50,000 this needs an FIR, so make sure your complaint has been registered as one."}{" "}
            (MHA SOP for CFCFRMS, section 11, Process 1.)
          </li>
          <li>
            Otherwise, you or the police can apply to the magistrate&apos;s court, or to a Lok Adalat, for an
            order to restore the money.
          </li>
          <li>Keep your acknowledgement number. Every bank and police station uses it to find your case.</li>
        </ol>
      </section>
      <p className="text-faint text-xs">
        {c.complete
          ? "Every bank on the trail has answered."
          : "Some banks have not answered yet, so these figures can still grow."}
      </p>
    </>
  );
}
