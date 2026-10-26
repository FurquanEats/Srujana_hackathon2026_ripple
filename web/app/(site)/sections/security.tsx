import { PixelHeading } from "@/components/pixel-heading";

const FACTS = [
  {
    title: "One process per institution",
    body: "Each bank's node runs as its own process with its own database, and sees only that bank's accounts.",
  },
  {
    title: "Mutual TLS",
    body: "Every connection between institutions presents a certificate on both sides, issued by the network's own authority.",
  },
  {
    title: "Signed messages",
    body: "Every notice and answer is signed and dated. A replayed or altered message is refused.",
  },
  {
    title: "Append-only audit log",
    body: "Each node records every notice, lien and answer in a chained log that shows any later change.",
  },
] as const;

export function Security() {
  return (
    <section id="security" aria-label="Security" className="relative z-10 scroll-mt-14 px-5 py-28 md:py-40">
      <div className="mx-auto max-w-6xl">
        <PixelHeading text="Security" className="text-center text-[24px] md:text-[30px]" />
        <dl className="mt-16 grid gap-x-10 gap-y-12 sm:grid-cols-2">
          {FACTS.map((fact, i) => (
            <div key={fact.title} className="grid grid-cols-[2rem_1fr] gap-x-3">
              <dt className="pixel col-span-2 grid grid-cols-subgrid text-xl">
                <span aria-hidden className="text-sm leading-[1.6] text-faint">
                  0{i + 1}
                </span>
                {fact.title}
              </dt>
              <dd className="col-start-2 mt-3 max-w-[44ch] text-sm leading-relaxed text-muted">
                {fact.body}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
