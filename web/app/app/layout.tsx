import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { CommandPalette } from "@/components/workspace/command-palette";
import { SideNav } from "@/components/workspace/side-nav";
import { LIVE, now } from "@/lib/gateway/source";
import { NAV } from "@/lib/nav";
import { institutionName, roleLabel } from "@/lib/personas";
import { currentSession } from "@/lib/session";
import { formatIst } from "@/lib/format";

import { signOut } from "../sign-in/actions";
import { resetDemoData, toggleTheme } from "./shell-actions";

export const dynamic = "force-dynamic";

/** The workspace shell: the role's sidebar, and a top bar with the institution, role and simulated clock. */
export default async function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const session = await currentSession();
  if (!session) redirect("/sign-in");
  const theme = (await cookies()).get("ripple_theme")?.value === "light" ? "tone-light" : "tone-dark";
  const items = NAV[session.role];
  let clock = "";
  try {
    clock = formatIst(await now(session));
  } catch {
    clock = "Network not reachable";
  }
  return (
    <div className={`${theme} workspace min-h-dvh`}>
      <div className="flex min-h-dvh flex-col md:flex-row">
        <aside className="border-line md:w-60 md:shrink-0 md:border-r">
          <div className="flex h-14 items-center justify-between px-4 md:px-5">
            <Link href="/" className="pixel text-lg" aria-label="Ripple, home">
              Ripple
            </Link>
            <span className="text-faint text-xs md:hidden">{roleLabel(session.role)}</span>
          </div>
          <SideNav items={items} />
          <div className="hidden px-5 py-6 md:block">
            <p className="text-faint text-[11px] leading-relaxed">
              {LIVE
                ? "Live: every page reads the running network through the gateway."
                : "Demo data: responses saved from a real run of the network. Your changes stay in this browser."}
            </p>
            {!LIVE && (
              <form action={resetDemoData} className="mt-2">
                <button className="text-muted text-[11px] underline underline-offset-2 hover:text-[var(--fg)]">
                  Undo my changes
                </button>
              </form>
            )}
          </div>
        </aside>
        <div className="min-w-0 flex-1">
          <header className="border-line flex min-h-14 flex-wrap items-center gap-x-4 gap-y-1 border-b px-4 py-2 text-[13px] md:px-8">
            <span className="text-fg">
              {session.member ? institutionName(session.member) : "All institutions"}
            </span>
            <span className="text-faint hidden sm:inline">·</span>
            <span className="text-muted">{roleLabel(session.role)}</span>
            <span
              className="text-faint ml-auto font-mono text-xs tabular-nums"
              title="The network's simulated time"
            >
              {clock}
            </span>
            <CommandPalette items={items} />
            <form action={toggleTheme}>
              <input type="hidden" name="back" value={items[0]?.href ?? "/app"} />
              <button
                className="text-muted hover:text-[var(--fg)]"
                aria-label="Switch between dark and light"
              >
                {theme === "tone-dark" ? "Light" : "Dark"}
              </button>
            </form>
            <form action={signOut}>
              <button className="text-muted hover:text-[var(--fg)]">Sign out</button>
            </form>
          </header>
          <main className="mx-auto max-w-[1180px] px-4 py-8 md:px-8 md:py-10">{children}</main>
        </div>
      </div>
    </div>
  );
}
