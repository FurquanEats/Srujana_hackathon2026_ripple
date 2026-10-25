import type { Metadata } from "next";
import Link from "next/link";

import { Attention, Explainer } from "@/components/workspace/attention";
import { Filters } from "@/components/workspace/filters";
import { ReleaseForm } from "@/components/workspace/release-form";
import { Empty, Held, Money, Notice, PageHeader } from "@/components/workspace/ui";
import { formatIst } from "@/lib/format";
import { liens } from "@/lib/gateway/source";
import { requireRole } from "@/lib/guard";

import { releaseLienAction } from "../actions";

export const metadata: Metadata = { title: "Liens" };

type Search = Promise<{ error?: string; done?: string; state?: string; q?: string }>;

export default async function LiensPage({ searchParams }: { searchParams: Search }) {
  const session = await requireRole("nodal_officer");
  const { error, done, state, q } = await searchParams;
  const all = [...(await liens(session))].sort((a, b) => b.placed_at.localeCompare(a.placed_at));
  const needle = (q ?? "").trim().toLowerCase();
  const list = all.filter(
    (l) =>
      (!state || (state === "active" ? !l.released_at : !!l.released_at)) &&
      (!needle || `${l.holder_name} ${l.account_number} ${l.ack_number}`.toLowerCase().includes(needle)),
  );
  const active = all.filter((l) => !l.released_at);
  const returned = all.filter((l) => l.returned_to_victim).reduce((s, l) => s + l.amount, 0);
  return (
    <>
      <PageHeader
        title="Liens"
        lead="Liens Ripple placed on traced amounts when answering CFCFRMS notices. Each covers the victim's money only, never the whole account."
      />
      {error && <Notice kind="error">{error}</Notice>}
      {done && <Notice kind="done">{done}</Notice>}
      <Attention
        tone={active.length ? "info" : "done"}
        title={
          active.length
            ? `${active.length} lien${active.length === 1 ? "" : "s"} in force`
            : "No liens in force"
        }
        facts={[
          { label: "Held on active liens", value: <Held paise={active.reduce((s, l) => s + l.amount, 0)} /> },
          { label: "Returned to victims", value: <Money paise={returned} /> },
          { label: "Released in all", value: all.length - active.length },
          { label: "Liens placed", value: all.length },
        ]}
      >
        Keep each lien until the police or a court orders a release, then record the order on the lien below.
      </Attention>
      <Filters
        values={{ state, q }}
        total={all.length}
        shown={list.length}
        fields={[
          {
            name: "state",
            label: "State",
            options: [
              { value: "active", label: "In force" },
              { value: "released", label: "Released" },
            ],
          },
          { name: "q", label: "Holder, account or complaint", placeholder: "Search" },
        ]}
      />
      {list.length === 0 ? (
        <Empty>No liens match.</Empty>
      ) : (
        <div className="grid gap-3">
          {list.map((l) => (
            <article key={l.lien_id} className="border-line border p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <p className="text-[15px]">
                  <Link href={`/app/accounts/${l.account_number}`} className="link">
                    {l.holder_name || l.account_number}
                  </Link>{" "}
                  <span className="text-faint font-mono text-xs">{l.account_number}</span>
                </p>
                {l.released_at ? (
                  <Money paise={l.amount} className="text-faint" />
                ) : (
                  <Held paise={l.amount} />
                )}
              </div>
              <p className="text-muted mt-1 text-sm">
                Complaint <span className="font-mono">{l.ack_number}</span> · {l.basis} · placed{" "}
                {formatIst(l.placed_at)}
              </p>
              {l.released_at ? (
                <p className="mt-2 text-sm">
                  Released {formatIst(l.released_at)}
                  {l.release_authority ? ` on the order of ${l.release_authority}` : ""}
                  {l.release_order ? ` (${l.release_order})` : ""}
                  {l.returned_to_victim ? ", returned to the victim" : ""}.
                </p>
              ) : (
                <details className="mt-3">
                  <summary className="link cursor-pointer text-sm">Record a release order</summary>
                  <div className="mt-3">
                    <ReleaseForm
                      action={releaseLienAction}
                      hidden={{ lien_id: l.lien_id, back: "/app/liens" }}
                      victimChoice
                    />
                  </div>
                </details>
              )}
            </article>
          ))}
        </div>
      )}
      <Explainer>
        <p>
          A lien stops a set amount from being spent; the rest of the account keeps working. Ripple liens the
          smaller of the money still traced and the amount reported (N3).
        </p>
        <p>
          The police can return held money to the victim as interim custody under BNSS 106(3): below ₹50,000
          without an FIR, above it with one (SOP 11, Process 1). Otherwise a court orders it.
        </p>
      </Explainer>
    </>
  );
}
