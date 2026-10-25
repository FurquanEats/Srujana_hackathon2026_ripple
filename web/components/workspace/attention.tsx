import Link from "next/link";

export type Tone = "urgent" | "action" | "done" | "info";

const TONES: Record<Tone, { border: string; label: string; dot: string }> = {
  urgent: { border: "border-l-red-500", label: "Needs you now", dot: "bg-red-500" },
  action: { border: "border-l-amber-500", label: "Next step", dot: "bg-amber-500" },
  done: { border: "border-l-[var(--color-accent)]", label: "Nothing to do", dot: "bg-accent" },
  info: { border: "border-l-[var(--muted)]", label: "For your information", dot: "bg-[var(--muted)]" },
};

export type QuickAction = { label: string; href: string; primary?: boolean };

/**
 * The first thing on a detail page: what state it is in, what the officer should do next and by when, and the
 * actions to do it, so attention goes where it is needed.
 */
export function Attention({
  tone,
  title,
  children,
  actions = [],
  facts = [],
}: {
  tone: Tone;
  title: string;
  children?: React.ReactNode;
  actions?: QuickAction[];
  facts?: { label: string; value: React.ReactNode }[];
}) {
  const t = TONES[tone];
  return (
    <section
      aria-label={t.label}
      className={`bg-panel mb-8 border border-l-4 border-line ${t.border} p-5 md:p-6`}
    >
      <p className="text-faint flex items-center gap-2 text-xs font-medium tracking-wide uppercase">
        <span aria-hidden className={`size-2 ${t.dot}`} />
        {t.label}
      </p>
      <h2 className="text-fg mt-2 text-xl font-semibold tracking-tight md:text-2xl">{title}</h2>
      {children && <div className="text-muted mt-2 max-w-3xl text-[15px] leading-relaxed">{children}</div>}
      {facts.length > 0 && (
        <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
          {facts.map((f) => (
            <div key={f.label}>
              <dt className="text-faint text-xs">{f.label}</dt>
              <dd className="text-fg mt-0.5 text-[15px]">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {actions.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-2">
          {actions.map((a) =>
            a.href.startsWith("#") ? (
              <a
                key={a.label}
                href={a.href}
                className={`button ${a.primary ? "button-solid" : "button-ghost"}`}
              >
                {a.label}
              </a>
            ) : (
              <Link
                key={a.label}
                href={a.href}
                className={`button ${a.primary ? "button-solid" : "button-ghost"}`}
              >
                {a.label}
              </Link>
            ),
          )}
        </div>
      )}
    </section>
  );
}

/** A short "how this works" note, folded by default so it never competes with the action. */
export function Explainer({
  title = "How this works",
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <details className="border-line my-8 border px-4 py-3 text-sm">
      <summary className="text-muted cursor-pointer select-none hover:text-[var(--fg)]">{title}</summary>
      <div className="text-muted mt-3 grid max-w-3xl gap-2 leading-relaxed">{children}</div>
    </details>
  );
}
