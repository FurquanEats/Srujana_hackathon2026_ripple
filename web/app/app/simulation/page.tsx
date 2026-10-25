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
      <section className="mt-12">
        <h2 className="pixel mb-2 text-lg">Today and with Ripple, side by side</h2>
        <p className="text-muted mb-4 max-w-3xl text-sm">
          The same complaint, answered by hand as banks do today and by Ripple. By hand, each payment out of
          M3&apos;s shop gets a notice for its full amount, and the shop&apos;s own money is held against the
          reported amount (figures from the PRD&apos;s demo story).
        </p>
        <div className="overflow-x-auto">
          <table className="table min-w-[640px]">
            <thead>
              <tr>
                <th>At M3&apos;s shop and the people it paid</th>
                <th className="text-right">Held by hand today</th>
                <th className="text-right">Held by Ripple</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>M3&apos;s own money (₹3,00,000 before the scam)</td>
                <td className="text-right font-mono">₹2,15,000</td>
                <td className="text-right font-mono">₹0</td>
              </tr>
              <tr>
                <td>Ravi Traders, paid for cement</td>
                <td className="text-right font-mono">₹2,00,000</td>
                <td className="text-right font-mono">₹2,00,000</td>
              </tr>
              <tr>
                <td>Galaxy Mobiles, paid ₹1,20,000 for two phones</td>
                <td className="text-right font-mono">₹1,20,000</td>
                <td className="text-right font-mono">₹50,000</td>
              </tr>
              <tr>
                <td>The shop assistant&apos;s ₹15,000 salary</td>
                <td className="text-right font-mono">₹15,000</td>
                <td className="text-right font-mono">₹0</td>
              </tr>
              <tr>
                <td>Time for the whole trail across six institutions</td>
                <td className="text-right">A bank at a time, each waiting for an officer</td>
                <td className="text-right">Under a second</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-faint mt-3 text-xs">
          Ripple follows the SOP&apos;s own Annexure V rule: a payment out takes the victim&apos;s money first
          and the holder&apos;s own money last, so money paid after the victim&apos;s ran out carries none of
          it.
        </p>
      </section>
    </>
  );
}
