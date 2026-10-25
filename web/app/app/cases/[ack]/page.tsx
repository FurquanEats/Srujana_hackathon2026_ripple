import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { TrailReplay } from "@/components/workspace/trail-replay";
import { Held, Money, PageHeader, Stat } from "@/components/workspace/ui";
import { GatewayFailure, trail } from "@/lib/gateway/source";
import type { Trail } from "@/lib/gateway/types";
import { requireRole } from "@/lib/guard";
import { INSTITUTIONS } from "@/lib/personas";

export const metadata: Metadata = { title: "Money trail" };

export default async function CasePage({ params }: { params: Promise<{ ack: string }> }) {
  const session = await requireRole("police_officer", "demo");
  const { ack } = await params;
  if (!/^[23]\d{13}$/.test(ack)) notFound();
  let t: Trail;
  try {
    t = await trail(session, ack);
  } catch (error) {
    if (error instanceof GatewayFailure && error.status === 404) notFound();
    throw error;
  }
  const names = Object.fromEntries(INSTITUTIONS.map((i) => [i.id, i.short]));
  const sum = t.held + t.cashed_out + t.off_network + t.not_found + t.waiting;
  return (
    <>
      <PageHeader
        title="Money trail"
        back={{ href: "/app/cases", label: "Cases" }}
        lead={
          <>
            NCRP acknowledgement <span className="font-mono">{t.ack_number}</span>. {t.accounts.length}{" "}
            accounts across {new Set(t.accounts.map((a) => a.member)).size} institutions.{" "}
            {t.complete ? "Every bank has answered." : "Some banks have not answered yet."}
          </>
        }
      />
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-6">
        <Stat label="Reported">
          <Money paise={t.reported} />
        </Stat>
        <Stat label="Held">
          <Held paise={t.held} />
        </Stat>
        <Stat label="Cashed out">
          <Money paise={t.cashed_out} />
        </Stat>
        <Stat label="Off network">
          <Money paise={t.off_network} />
        </Stat>
        <Stat label="Not found">
          <Money paise={t.not_found} />
        </Stat>
        <Stat label="Waiting">
          <Money paise={t.waiting} />
        </Stat>
      </div>
      <p className="text-faint mb-10 text-xs">
        {sum === t.reported
          ? "Held, cashed out, off network, not found and waiting add up to the amount reported, to the rupee."
          : "The totals do not yet add up to the amount reported: a bank's answer is still on its way."}
      </p>
      <TrailReplay trail={t} institutions={names} />
    </>
  );
}
