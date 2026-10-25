"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { resetDemo } from "@/lib/gateway/source";

export async function toggleTheme(form: FormData): Promise<void> {
  const jar = await cookies();
  const next = jar.get("ripple_theme")?.value === "light" ? "dark" : "light";
  jar.set("ripple_theme", next, { sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 365 });
  const back = String(form.get("back") ?? "/app");
  redirect(back.startsWith("/app") ? back : "/app");
}

export async function resetDemoData(): Promise<void> {
  await resetDemo();
  redirect("/app");
}
