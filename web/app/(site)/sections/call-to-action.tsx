import Link from "next/link";

import { PixelHeading } from "@/components/pixel-heading";

export function CallToAction() {
  return (
    <section aria-label="Open the workspace" className="relative z-10 px-5 py-28 text-center md:py-40">
      <PixelHeading
        text="Every rupee, accounted for."
        className="mx-auto max-w-[14ch] text-3xl md:text-5xl"
      />
      <p className="mx-auto mt-5 max-w-[44ch] text-[15px] leading-relaxed text-grey-300">
        Open a case and replay the money hop by hop, from the victim&apos;s bank to every account it reached.
      </p>
      <Link href="/app/cases" className="button button-solid mt-9">
        See a trail in the workspace
      </Link>
    </section>
  );
}
