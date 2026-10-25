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
        <PixelHeading text="Security" className="text-center text-3xl md:text-4xl" />
        <dl className="mt-16 grid gap-x-10 gap-y-12 sm:grid-cols-2">
          {FACTS.map((fact, i) => (
            <div key={fact.title} className="flex gap-5">
              <span aria-hidden className="pixel text-sm text-grey-500">
                0{i + 1}
              </span>
              <div>
                <dt className="pixel text-xl">{fact.title}</dt>
                <dd className="mt-3 max-w-[44ch] text-sm leading-relaxed text-grey-300">{fact.body}</dd>
              </div>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
