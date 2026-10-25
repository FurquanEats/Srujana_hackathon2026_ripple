import { PixelHeading } from "@/components/pixel-heading";
import { Term } from "@/components/term";

const RULES = [
  {
    title: "MHA SOP for NCRP-CFCFRMS",
    body: (
      <>
        Ripple answers each notice with what the SOP asks a bank to report: the amount held, the onward
        transfers and the exit details.
      </>
    ),
  },
  {
    title: "RBI draft directions on money mules",
    body: (
      <>
        Ripple runs the <Term name="debitHold" /> with its customer notice and every deadline, from 20 to 60
        days.
      </>
    ),
  },
  {
    title: "BNSS s.168 and s.94",
    body: (
      <>
        Every lien Ripple places rests on the police notice under these sections, and on the traced amount
        only.
      </>
    ),
  },
  {
    title: "PMLA reporting",
    body: (
      <>
        Ripple drafts the <Term name="str" /> for the bank&apos;s principal officer, who reviews and files it.
      </>
    ),
  },
] as const;

export function Rules() {
  return (
    <section
      id="legal-basis"
      aria-label="Built on the rules"
      className="relative z-10 scroll-mt-14 px-5 py-28 md:py-40"
    >
      <div className="mx-auto max-w-6xl">
        <PixelHeading text="Built on the rules" className="text-center text-3xl md:text-4xl" />
        <p className="mx-auto mt-5 max-w-[50ch] text-center text-[15px] leading-relaxed text-grey-300">
          Every action Ripple proposes sits on a named legal basis. Actions the law gives only to the police
          or the courts stay with them.
        </p>
        <ul className="mt-16 grid gap-px bg-grey-900 sm:grid-cols-2 lg:grid-cols-4">
          {RULES.map((rule) => (
            <li key={rule.title} className="bg-ink p-7">
              <h3 className="pixel text-lg">{rule.title}</h3>
              <p className="mt-4 text-sm leading-relaxed text-grey-300">{rule.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
