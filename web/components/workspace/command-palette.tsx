"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { NavItem } from "@/lib/nav";

/** Ctrl+K (or Cmd+K): jump to any page this role can open. */
export function CommandPalette({ items }: { items: NavItem[] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const router = useRouter();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  const matches = items.filter((i) => `${i.label} ${i.hint}`.toLowerCase().includes(query.toLowerCase()));
  const go = (href: string) => {
    setOpen(false);
    setQuery("");
    router.push(href);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="chip text-muted hidden hover:text-[var(--fg)] sm:inline-flex"
      >
        Go to <kbd className="font-mono text-[11px]">Ctrl K</kbd>
      </button>
      <dialog
        ref={dialog}
        onClose={() => setOpen(false)}
        aria-label="Go to a page"
        className="m-auto mt-[15vh] w-[min(32rem,calc(100vw-2rem))] border border-line bg-surface p-0 text-fg backdrop:bg-black/60"
      >
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && matches[0] && go(matches[0].href)}
          placeholder="Type a page name"
          aria-label="Page name"
          className="field border-0 border-b"
        />
        <ul className="max-h-72 overflow-y-auto py-1">
          {matches.map((i) => (
            <li key={i.href}>
              <button
                onClick={() => go(i.href)}
                className="block w-full px-4 py-2.5 text-left text-sm hover:bg-[var(--hover)]"
              >
                {i.label}
                <span className="text-faint ml-2 text-xs">{i.hint}</span>
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="text-faint px-4 py-3 text-sm">No page matches.</li>}
        </ul>
      </dialog>
    </>
  );
}
