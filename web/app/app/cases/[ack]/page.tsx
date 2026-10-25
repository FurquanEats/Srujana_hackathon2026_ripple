import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Attention, Explainer } from "@/components/workspace/attention";
import { ReleaseForm } from "@/components/workspace/release-form";
import { TrailReplay } from "@/components/workspace/trail-replay";
import { Held, Money, Notice, PageHeader, Stat } from "@/components/workspace/ui";
import { formatInr, formatIst } from "@/lib/format";
import { GatewayFailure, releasedLiens, trail } from "@/lib/gateway/source";
import type { Trail } from "@/lib/gateway/types";
import { requireRole, type Outcome } from "@/lib/guard";

import { policeReleaseAction } from "../../actions";

const FIFTY_THOUSAND = 50_000_00;
import { INSTITUTIONS } from "@/lib/personas";

export const metadata: Metadata = { title: "Money trail" };

export default async function CasePage({
  params,
  searchParams,
}: {
  params: Promise<{ ack: string }>;
  searchParams: Outcome;
}) {
  const session = await requireRole("police_officer", "demo");
  const { ack } = await params;
  const { error, done } = await searchParams;
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
  const released = await releasedLiens();
  const heldAccounts = t.accounts.filter((a) => a.held > 0 && a.lien_id && a.member);
  const stillHeld = heldAccounts
    .filter((a) => !released.has(a.lien_id ?? ""))
    .reduce((s, a) => s + a.held, 0);
  const police = session.role === "police_officer";
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
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      <Attention
        tone={!t.complete ? "info" : stillHeld > 0 ? "action" : "done"}
        title={
          !t.complete
            ? "Some banks have not answered yet"
            : stillHeld > 0
              ? `${formatInr(stillHeld)} is held for the victim across ${heldAccounts.length} account${heldAccounts.length === 1 ? "" : "s"}`
              : "Nothing left to return on this trail"
        }
        actions={[
          ...(police && stillHeld > 0
            ? [{ label: "Return money to the victim", href: "#return", primary: true }]
            : []),
          { label: "Replay the trail", href: "#graph" },
          ...(t.accounts.some((a) => a.exits.length) ? [{ label: "Cash-out leads", href: "#exits" }] : []),
        ]}
      >
        {stillHeld > 0
          ? `You can return held money as interim custody under BNSS 106(3): ${stillHeld < FIFTY_THOUSAND ? "below ₹50,000 no FIR is needed" : "above ₹50,000 this needs an FIR"} (SOP 11, Process 1). Follow the cash-outs from their ATM and exchange identifiers.`
          : "Every rupee reported is accounted for below."}
      </Attention>
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
      <p className="text-muted mb-4 text-sm">
        Each column is a <strong className="font-medium">layer</strong>: layer 1 is the account the victim
        paid, layer 2 the accounts it paid on, and so on. A green box still holds the victim&apos;s money
        under lien.
      </p>
      <TrailReplay trail={t} institutions={names} />
      {police && heldAccounts.length > 0 && (
        <section id="return" className="mt-10 scroll-mt-6">
          <h2 className="pixel mb-1 text-lg">Return held money to the victim</h2>
          <div className="text-muted mb-4 grid max-w-3xl gap-2 text-sm leading-relaxed">
            <p>
              These accounts still hold the victim&apos;s money under a lien. You can order each bank to give
              it back to the victim as interim custody under BNSS section 106(3): below ₹50,000 without an
              FIR, above it with one (SOP section 11, Process 1). The bank records your order against its
              lien, and the victim&apos;s status page shows the money returning.
            </p>
            <p>
              <strong className="font-medium text-[var(--fg)]">Layer</strong> is how many transfers the money
              made before reaching the account: layer 1 is the account the victim paid, layer 2 an account
              that one paid on to, and so on. An account at a higher layer is often a shop paid for real
              goods, so check its bank&apos;s grievance before ordering a return from it.
            </p>
          </div>
          <div className="grid gap-3">
            {heldAccounts.map((a) => {
              const r = released.get(a.lien_id ?? "");
              return (
                <article key={a.notice_id} className="border-line border p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-3">
                    <p className="text-[15px]">
                      {a.holder_name}{" "}
                      <span className="text-faint text-sm">
                        · {names[a.member ?? ""] ?? a.member} · layer {a.layer}
                      </span>
                    </p>
                    <Held paise={a.held} />
                  </div>
                  {r ? (
                    <p className="mt-2 text-sm">
                      Release ordered {formatIst(r.at)} ({r.order}){r.toVictim ? ", to the victim" : ""}.
                    </p>
                  ) : (
                    <details className="mt-3">
                      <summary className="link cursor-pointer text-sm">Order the bank to return it</summary>
                      <div className="mt-3">
                        <ReleaseForm
                          action={policeReleaseAction}
                          hidden={{ lien_id: a.lien_id ?? "", member: a.member ?? "", ack: t.ack_number }}
                          victimChoice={false}
                          authority="Cyber Crime Police Station, Hyderabad"
                          submit="Send the release order"
                        />
                      </div>
                    </details>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      )}
      <Explainer>
        <p>
          CFCFRMS sent a notice to each bank the money reached; each bank&apos;s Ripple node answered at once
          with the traced amount, the lien and the next hops (H2, H3).
        </p>
        <p>
          Held, cashed out, off network, not found and waiting always add up to the amount reported. When two
          victims&apos; money meets in one account, the held money is split as the SOP&apos;s Annexure V says
          (H4).
        </p>
      </Explainer>
    </>
  );
}
