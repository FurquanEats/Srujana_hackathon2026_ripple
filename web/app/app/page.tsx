import { redirect } from "next/navigation";

import { homeFor } from "@/lib/nav";
import { currentSession } from "@/lib/session";

export default async function WorkspaceHome() {
  const session = await currentSession();
  redirect(session ? homeFor(session.role) : "/sign-in");
}
