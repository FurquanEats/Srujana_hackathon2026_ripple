import Link from "next/link";

import { formatInr } from "@/lib/format";

/** Page title in the pixel face, at the home page's heading size. */
export function PageHeader({
  title,
  lead,
  back,
}: {
  title: string;
  lead?: React.ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <div className="mb-8">
      {back && (
        <Link href={back.href} className="text-muted mb-4 inline-block text-[13px] hover:text-[var(--fg)]">
          ← {back.label}
        </Link>
      )}
      <h1 className="pixel text-[26px] md:text-[30px]">{title}</h1>
      {lead && <p className="text-muted mt-2 max-w-2xl text-sm leading-relaxed">{lead}</p>}
    </div>
  );
}

/** Money that is traced or held is the only thing shown in green. */
export function Held({ paise }: { paise: number }) {
  return <span className="bg-accent px-1.5 font-mono text-ink tabular-nums">{formatInr(paise)}</span>;
}

export function Money({ paise, className = "" }: { paise: number; className?: string }) {
  return <span className={`font-mono tabular-nums ${className}`}>{formatInr(paise)}</span>;
}

export function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-line border p-4">
      <p className="text-faint text-xs">{label}</p>
      <p className="mt-1 text-lg">{children}</p>
    </div>
  );
}

export function Notice({ kind, children }: { kind: "error" | "done"; children: React.ReactNode }) {
  return (
    <p
      role={kind === "error" ? "alert" : "status"}
      className={`mb-6 border px-4 py-3 text-sm ${kind === "error" ? "border-red-500 text-red-500" : "border-accent text-fg"}`}
    >
      {children}
    </p>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="border-line text-muted border border-dashed px-4 py-10 text-center text-sm">{children}</p>
  );
}

const PRIORITY: Record<string, string> = { high: "High", medium: "Medium", low: "Low" };

export function Priority({ level }: { level: string }) {
  const dot = level === "high" ? "bg-red-500" : level === "medium" ? "bg-amber-500" : "bg-grey-500";
  return (
    <span className="chip">
      <span aria-hidden className={`size-1.5 ${dot}`} />
      {PRIORITY[level] ?? level}
    </span>
  );
}

export function Masked({ account }: { account: string | null }) {
  if (!account) return <span className="text-faint">None</span>;
  return <span className="font-mono">{account}</span>;
}
