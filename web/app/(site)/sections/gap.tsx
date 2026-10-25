import { PixelHeading } from "@/components/pixel-heading";
import { Term } from "@/components/term";

const FIGURES = [
  { value: "Rs 52,969 CR", line: "reported lost to cyber fraud" },
  { value: "Rs 7,647 CR", line: "held before it reached the criminals" },
  { value: "Rs 167 CR", line: "returned to victims" },
] as const;

export function Gap() {
  return (
    <section aria-labelledby="gap-title" className="relative z-10 px-5 py-28 md:py-40">
      <div className="mx-auto max-w-6xl">
        <PixelHeading text="The gap today" className="text-center text-[24px] md:text-[30px]" />
        <p
          id="gap-title"
          className="mx-auto mt-5 max-w-[52ch] text-center text-[14px] leading-relaxed text-muted"
        >
          <Term name="cfcfrms" /> follows a victim&apos;s money one bank at a time, and each step waits for a
          person at that bank. From April 2021 to November 2025:
        </p>
        <dl className="mt-16 grid gap-12 md:grid-cols-3 md:gap-6">
          {FIGURES.map((f) => (
            <div key={f.value} className="text-center">
              <dt className="sr-only">{f.line}</dt>
              <dd className="pixel text-[36px] md:text-[48px]">{f.value}</dd>
              <dd className="mt-3 text-sm text-muted">{f.line}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-14 text-center text-xs text-faint">
          Source: MHA Standard Operating Procedure for NCRP-CFCFRMS, January 2026. CR is crore.
        </p>
      </div>
    </section>
  );
}
