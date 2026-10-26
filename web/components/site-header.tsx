import Link from "next/link";

/** A small centred wordmark fixed at the top, with a soft blur behind it while the page scrolls. */
export function SiteHeader() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 text-white mix-blend-difference">
      <nav
        aria-label="Main"
        className="mx-auto grid h-14 max-w-[1440px] grid-cols-3 items-center px-5 md:px-8"
      >
        <Link href="/#how-it-works" className="justify-self-start text-[13px] text-white/70 hover:text-white">
          How it works
        </Link>
        <Link href="/" className="pixel justify-self-center text-lg" aria-label="Ripple, home">
          Ripple
        </Link>
        <Link href="/app" className="justify-self-end text-[13px] text-white/70 hover:text-white">
          Workspace
        </Link>
      </nav>
    </header>
  );
}
