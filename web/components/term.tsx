"use client";

import { useId, useState } from "react";

import { TERMS, type TermKey } from "@/lib/terms";

/**
 * A technical or legal term with its plain explanation, shown on hover or keyboard focus and read by screen
 * readers as the term's description.
 */
export function Term({
  name,
  children,
  below = false,
}: {
  name: TermKey;
  children?: React.ReactNode;
  /** Open below the term, for places where the space above is clipped (a table header inside a scroll box). */
  below?: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const term = TERMS[name];
  return (
    <span className="relative inline-block">
      <button
        type="button"
        aria-describedby={id}
        className="cursor-help border-b border-dotted border-current font-[inherit]"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
      >
        {children ?? term.label}
      </button>
      <span
        id={id}
        role="tooltip"
        className={`absolute ${below ? "top-full mt-2" : "bottom-full mb-2"} left-1/2 z-20 w-[min(18rem,80vw)] -translate-x-1/2 border border-grey-700 bg-ink p-3 text-left text-[13px] leading-snug font-normal whitespace-normal text-grey-300 normal-case tracking-normal shadow-xl ${open ? "block" : "hidden"}`}
      >
        {term.text}
      </span>
    </span>
  );
}
