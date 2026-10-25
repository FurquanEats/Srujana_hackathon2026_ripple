import Link from "next/link";

const LINKS = [
  { href: "/#how-it-works", label: "How it works" },
  { href: "/#security", label: "Security" },
  { href: "/#legal-basis", label: "Legal basis" },
  { href: "https://github.com/FurquanEats/Srujana_hackathon2026_ripple", label: "Source code" },
] as const;

export function SiteFooter() {
  return (
    <footer className="relative z-10 overflow-hidden px-5 pt-20 md:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <nav aria-label="Footer">
          <ul className="pixel flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted">
            {LINKS.map((l) => (
              <li key={l.href}>
                <Link href={l.href} className="hover:text-white">
                  {l.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <p className="text-xs text-faint">Prototype for Srujana Tech Fest 2026. All data is synthetic.</p>
      </div>
      <p
        aria-hidden
        className="pixel mt-8 -mb-[0.18em] text-center text-[25vw] leading-none text-grey-900 select-none md:text-[24vw]"
      >
        Ripple
      </p>
    </footer>
  );
}
