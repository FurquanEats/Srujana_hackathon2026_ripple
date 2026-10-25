import type { Metadata } from "next";
import Link from "next/link";

import { holderPersonas, victimPersonas } from "@/lib/gateway/source";
import { INSTITUTIONS, institutionName, ROLES } from "@/lib/personas";

import { signIn } from "./actions";
import { RolePicker } from "./role-picker";

export const metadata: Metadata = { title: "Sign in" };

const ERRORS: Record<string, string> = {
  disabled: "Demo sign-in is turned off on this server. Set RIPPLE_DEMO=1 to turn it on.",
  role: "Choose a role.",
  member: "Choose the institution you work for.",
  holder: "Choose whose account you are.",
};

export default async function SignInPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const { error } = await searchParams;
  return (
    <main className="tone-light flex min-h-dvh items-center justify-center px-4 py-16">
      <div className="w-full max-w-[560px]">
        <Link href="/" className="pixel block text-center text-xl" aria-label="Ripple, home">
          Ripple
        </Link>
        <h1 className="pixel mt-10 text-center text-[30px]">Sign in to the workspace</h1>
        <p className="text-muted mx-auto mt-3 max-w-sm text-center text-sm">
          This is a demonstration on synthetic data, so there is no password. Choose who you are, and Ripple
          shows what that officer would see.
        </p>
        {error && ERRORS[error] && (
          <p role="alert" className="mt-6 border border-red-700 px-3 py-2 text-sm text-red-700">
            {ERRORS[error]}
          </p>
        )}
        <form action={signIn} className="mt-8 border border-line p-5 sm:p-6">
          <RolePicker
            roles={ROLES}
            institutions={INSTITUTIONS}
            holders={holderPersonas().map((h) => ({
              value: `${h.member}:${h.account}`,
              label: `${h.name}, ${institutionName(h.member, true)}`,
            }))}
            complaints={victimPersonas().map((v) => ({
              value: v.ack,
              label: `${v.name}, complaint ${v.ack}`,
            }))}
          />
          <button type="submit" className="button button-solid mt-6 w-full">
            Continue
          </button>
          <p className="text-faint mt-4 text-center text-xs">
            Every name, account and amount here is made up. No real bank or person is involved.
          </p>
        </form>
      </div>
    </main>
  );
}
