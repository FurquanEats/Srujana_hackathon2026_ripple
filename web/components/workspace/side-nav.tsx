"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { NavItem } from "@/lib/nav";

export function SideNav({ items }: { items: NavItem[] }) {
  const path = usePathname();
  return (
    <nav
      aria-label="Workspace"
      className="border-line flex gap-1 overflow-x-auto border-b px-2 pb-2 md:block md:border-0 md:px-3 md:pb-0"
    >
      {items.map((item) => {
        const active = path === item.href || path.startsWith(item.href + "/");
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`block shrink-0 px-3 py-2 text-[13px] md:px-2 ${active ? "bg-hover text-fg" : "text-muted hover:text-[var(--fg)]"}`}
          >
            {active && <span aria-hidden className="mr-2 inline-block size-1.5 bg-accent align-middle" />}
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
