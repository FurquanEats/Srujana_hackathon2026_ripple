import { PixelHeading } from "@/components/pixel-heading";
import { Term } from "@/components/term";
import { formatInr } from "@/lib/format";

/** M3's account in the demo story: Rs 2,50,000 of victim money arrives on top of Rs 3,00,000 of the shop's own. */
const LINES = [
  { label: "Shop's own money", amount: 300_000_00, victim: 0 },
  { label: "Victim's money received", amount: 250_000_00, victim: 250_000_00 },
  { label: "Paid to Ravi Traders", amount: -200_000_00, victim: -200_000_00 },
  { label: "Paid to Galaxy Mobiles", amount: -120_000_00, victim: -50_000_00 },
  { label: "Salary to the shop assistant", amount: -15_000_00, victim: 0 },
] as const;

export function Fair() {
  return (
    <section
      aria-labelledby="fair-title"
      className="on-paper relative z-10 bg-paper px-5 py-28 text-ink md:py-40"
    >
      <div className="mx-auto grid max-w-6xl items-center gap-16 md:grid-cols-2">
        <div>
          <PixelHeading text="Only the victim's money is held." className="text-3xl md:text-[42px]" />
          <p id="fair-title" className="mt-6 max-w-[48ch] text-[15px] leading-relaxed text-grey-700">
            Ripple follows the rule in the MHA SOP&apos;s own examples: a payment out of an account carries
            the victims&apos; money first and the holder&apos;s own money last. The holder&apos;s own money is
            never placed under a <Term name="lien" />.
          </p>
          <p className="mt-4 max-w-[48ch] text-[15px] leading-relaxed text-grey-700">
            A business that received victim money in good faith uploads its invoices. They are checked against
            the bank&apos;s own records, so the bank can file its grievance for the business within a day,
            against the seven days the SOP allows.
          </p>
        </div>
        <figure className="border border-black/10 bg-white p-6 shadow-[0_30px_80px_-40px_rgba(0,0,0,0.35)] md:p-8">
          <figcaption className="pixel text-sm text-grey-500">One account, traced</figcaption>
          <table className="mt-5 w-full text-left text-sm">
            <thead className="sr-only">
              <tr>
                <th>Entry</th>
                <th>Amount</th>
                <th>Victim money in it</th>
              </tr>
            </thead>
            <tbody>
              {LINES.map((line) => (
                <tr key={line.label} className="border-t border-black/10">
                  <td className="py-3 pr-3 text-grey-700">{line.label}</td>
                  <td className="py-3 pr-3 text-right font-mono tabular-nums">{formatInr(line.amount)}</td>
                  <td className="w-24 py-3 text-right">
                    {line.victim !== 0 && (
                      <span className="inline-block bg-cyan px-1.5 py-0.5 font-mono text-[12px] text-ink tabular-nums">
                        {formatInr(Math.abs(line.victim))}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-5 text-[13px] leading-relaxed text-grey-700">
            The cyan figures are the victim&apos;s money. The salary was paid after the victim&apos;s money
            had run out, so it carries none of it, and no notice goes to the shop assistant.
          </p>
        </figure>
      </div>
    </section>
  );
}
