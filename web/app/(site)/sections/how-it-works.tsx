import { PixelHeading } from "@/components/pixel-heading";
import { Term } from "@/components/term";
import { TileArt } from "@/components/tile-art";

const STEPS = [
  {
    title: "A notice arrives",
    body: (
      <>
        <Term name="cfcfrms" /> asks the bank that received a victim&apos;s money to hold it. The notice names
        the payment and the victim&apos;s <Term name="ncrp" />.
      </>
    ),
  },
  {
    title: "The node traces and liens",
    body: (
      <>
        The bank&apos;s Ripple node works out the <Term name="tracedAmount" /> in the account and places a{" "}
        <Term name="lien" /> on that amount only, in under a second.
      </>
    ),
  },
  {
    title: "The next bank is notified",
    body: (
      <>
        The node reports onward transfers and cash withdrawals. CFCFRMS notifies the next bank at once, so the
        trail completes across institutions without waiting for anyone.
      </>
    ),
  },
] as const;

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      aria-label="How it works"
      className="relative z-10 scroll-mt-14 px-5 py-28 md:py-40"
    >
      <div className="mx-auto grid max-w-6xl gap-16 md:grid-cols-2 md:gap-10">
        <div className="md:order-2">
          <div className="md:sticky md:top-28">
            <TileArt className="w-full" />
          </div>
        </div>
        <ol className="flex flex-col gap-24 md:gap-[38vh] md:py-[12vh]">
          {STEPS.map((step, i) => (
            <li key={step.title} className="max-w-md">
              <p className="pixel text-sm text-faint">Step {i + 1}</p>
              <PixelHeading as="h3" text={step.title} className="mt-3 text-[24px] md:text-[30px]" />
              <p className="mt-5 text-[14px] leading-relaxed text-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
