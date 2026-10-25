import type { Metadata } from "next";

import { Notice, PageHeader } from "@/components/workspace/ui";
import { LIVE } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

import { playDemo } from "../actions";

export const metadata: Metadata = { title: "Simulation" };

export default async function SimulationPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  await requireRole("demo");
  const { error } = await searchParams;
  return (
    <>
      <PageHeader
        title="Simulation"
        lead="Play the PRD's demo story on the network: a retired teacher is pushed into a digital-arrest scam and sends ₹8,00,000 by RTGS. Within eight minutes the money splits across mule accounts at four institutions, two ATM withdrawals and a crypto exchange. She calls 1930 at minute 12, and Ripple traces it across six institutions."
      />
      {error && <Notice kind="error">{error}</Notice>}
      <ol className="text-muted mb-8 grid max-w-2xl list-decimal gap-2 pl-5 text-sm leading-relaxed">
        <li>
          The story&apos;s payments post to each bank&apos;s node, as the bank&apos;s core banking system
          would.
        </li>
        <li>The complaint goes to the simulated CFCFRMS hub, which sends a notice to the first bank.</li>
        <li>
          Each bank&apos;s Ripple node traces the victim&apos;s money, places a lien on the traced amount and
          names the next hops.
        </li>
        <li>You land on the trail, where the replay shows the money moving hop by hop.</li>
      </ol>
      <form action={playDemo}>
        <button className="button button-solid">Play the demo story</button>
      </form>
      {!LIVE && (
        <p className="text-faint mt-4 max-w-2xl text-xs">
          This copy runs on saved data, so the button opens the trail recorded when the story last ran on the
          network. With RIPPLE_GATEWAY=live it plays the story again, with fresh account numbers.
        </p>
      )}
    </>
  );
}
