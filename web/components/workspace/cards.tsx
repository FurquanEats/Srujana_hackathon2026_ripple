import Link from "next/link";

/** A card that opens something: the whole card is the target, with an arrow that moves on hover. */
export function CardLink({
  href,
  title,
  children,
}: {
  href: string;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <Link href={href} className="card-link">
      <span className="flex items-baseline justify-between gap-3">
        <span className="text-fg text-sm">{title}</span>
        <span aria-hidden className="go">
          →
        </span>
      </span>
      {children && <span className="text-muted mt-1 block text-[13px] leading-snug">{children}</span>}
    </Link>
  );
}

/** A big number with its label, optionally opening the list behind it. */
export function Metric({
  label,
  value,
  href,
  note,
}: {
  label: string;
  value: React.ReactNode;
  href?: string;
  note?: string;
}) {
  const body = (
    <>
      <span className="text-faint flex items-center justify-between text-xs">
        {label}
        {href && (
          <span aria-hidden className="go">
            →
          </span>
        )}
      </span>
      <span className="mt-1 block text-2xl tabular-nums">{value}</span>
      {note && <span className="text-faint mt-1 block text-xs">{note}</span>}
    </>
  );
  return href ? (
    <Link href={href} className="card-link">
      {body}
    </Link>
  ) : (
    <div className="border-line border p-4">{body}</div>
  );
}

export function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-10">
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="pixel text-lg">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
