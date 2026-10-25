import Link from "next/link";

import { PixelHeading } from "@/components/pixel-heading";
import { TileArt } from "@/components/tile-art";

export function Hero() {
  return (
    <section className="relative z-10 flex min-h-svh flex-col items-center justify-end px-5 pt-24 pb-16 text-center md:pb-20">
      <TileArt className="mb-6 w-full max-w-[640px] md:mb-10" />
      <PixelHeading
        as="h1"
        text="Follow the money. Hold only what is traced."
        className="max-w-[18ch] text-[28px] md:text-[34px]"
      />
      <p className="mt-6 max-w-[46ch] text-[14px] leading-relaxed text-muted md:text-base">
        Ripple answers cyber-fraud notices for banks in seconds, tracing a victim&apos;s money across
        institutions and placing liens on the traced amount only.
      </p>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Link href="/app" className="button button-solid">
          Open the workspace
        </Link>
        <Link href="#how-it-works" className="button button-ghost">
          How it works
        </Link>
      </div>
    </section>
  );
}
