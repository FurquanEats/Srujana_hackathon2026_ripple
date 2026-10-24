"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AccountProfiles, EvidenceList, ModelContributions } from "@/components/Evidence";
import { FreezeList, RecoveryChart, RecoveryMetrics } from "@/components/FreezePlan";
import { MoneyGraph, ReplayControls } from "@/components/MoneyGraph";
import { Timeline, type CaseEvent } from "@/components/Timeline";
import { Button, Card, Dialog, ErrorNote, Icon, LoadingPanel, Notice, Spinner, TierBadge } from "@/components/ui";
import { api, money, prob, time, type CaseDetail, type InterdictionPlan } from "@/lib/api";

type Verdict = "confirmed" | "dismissed";

const SECTIONS = [
  ["evidence", "Evidence"],
  ["money-flow", "Money flow"],
  ["recovery", "Recovery over time"],
  ["freeze-plan", "Freeze plan"],
  ["timeline", "Timeline"],
] as const;

function DecisionDialog({ verdict, caseId, onCancel, onConfirm, busy }: {
  verdict: Verdict | null;
  caseId: string;
  onCancel: () => void;
  onConfirm: (v: Verdict) => void;
  busy: boolean;
}) {
  const confirming = verdict === "confirmed";
  return (
    <Dialog open={verdict !== null} onClose={busy ? () => {} : onCancel}
            title={confirming ? `Confirm ${caseId} as fraud?` : `Dismiss ${caseId}?`}
            description={confirming
              ? "Record that, after review, you judge this case to be fraud."
              : "Record that, after review, you judge this case not to be fraud."}
            footer={
              <>
                <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
                <Button variant="navy" onClick={() => verdict && onConfirm(verdict)} disabled={busy}>
                  {busy && <Spinner />}{confirming ? "Record: confirmed fraud" : "Record: dismissed"}
                </Button>
              </>
            }>
      <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted">
        <li>Your decision is used as feedback: Ripple re-weights its signal layers and re-ranks other open cases.</li>
        <li>It does <strong className="text-ink">not</strong> freeze any account, send a hold request or file a report. Those remain separate steps for an officer.</li>      </ul>
    </Dialog>
  );
}

export function Workbench() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [plan, setPlan] = useState<InterdictionPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<number | null>(null);
  const [asking, setAsking] = useState<Verdict | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [decision, setDecision] = useState<{ verdict: Verdict; message: string; at: string } | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([api.case(id), api.interdiction(id)])
      .then(([d, p]) => { setDetail(d); setPlan(p); })
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(load, [load]);

  const edges = useMemo(() => (detail ? [...detail.edges].sort((a, b) => a.ts.localeCompare(b.ts)) : []), [detail]);
  const accounts = useMemo(() => {
    if (!detail) return [];
    const held = new Map(plan?.holdings.map((h) => [h.account_id, h.tainted]) ?? []);
    return detail.nodes.map((n) => ({ id: n.id, role: n.role === "other" ? "victim" : n.role, risk: n.risk, holding: held.get(n.id) }));
  }, [detail, plan]);

  const events = useMemo<CaseEvent[]>(() => {
    if (!detail) return [];
    const out: CaseEvent[] = [{ ts: detail.opened_at, title: "Case opened", icon: "shield", detail: `${detail.tier} · probability ${prob(detail.probability)}` }];
    if (plan?.first_alert_at) out.push({ ts: plan.first_alert_at, title: "First alert on the money trail", icon: "critical",
      detail: plan.recoverable_at_first_alert != null ? `${money(plan.recoverable_at_first_alert)} was still recoverable` : undefined });
    if (detail.updated_at !== detail.opened_at) out.push({ ts: detail.updated_at, title: "Case last updated", icon: "clock" });
    if (detail.str_due) out.push({ ts: detail.str_due, title: "Suspicious transaction report due", icon: "draft" });
    if (decision) out.push({ ts: decision.at, title: decision.verdict === "confirmed" ? "Officer confirmed as fraud" : "Officer dismissed", icon: "check", detail: "Recorded in this session" });
    return out;
  }, [detail, plan, decision]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link href="/" className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-link hover:underline">
          <Icon name="arrowLeft" className="h-4 w-4" /> Case queue
        </Link>
        <ErrorNote title={`Could not load case ${id}`} error={error} onRetry={() => { setError(null); load(); }} />
      </div>
    );
  }
  if (!detail || !plan) return <LoadingPanel label={`Loading case ${id}…`} />;

  const currency = detail.timeline[0]?.currency ?? "INR";
  const at = step === null ? undefined : edges[step]?.ts;
  const status = decision?.verdict ?? detail.status;

  const decide = async (v: Verdict) => {
    setDeciding(true);
    setDecisionError(null);
    try {
      const r = await api.feedback(id, v);
      setDecision({
        verdict: v,
        at: new Date().toISOString(),
        message: `${v === "confirmed" ? "Confirmed" : "Dismissed"}. Detector weight ${r.weights_before.detector.toFixed(2)} → ${r.weights_after.detector.toFixed(2)}; ${r.requeued} other cases re-ranked.`,
      });
      setAsking(null);
    } catch (e) {
      setDecisionError((e as Error).message);
    } finally {
      setDeciding(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Identity, severity and decision */}
      <div>
        <Link href="/" className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-link hover:underline">
          <Icon name="arrowLeft" className="h-4 w-4" /> Case queue
        </Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="whitespace-nowrap font-mono text-2xl font-semibold tracking-tight text-navy sm:text-3xl">{detail.case_id}</h1>
              <TierBadge tier={detail.tier} />
              <span className={`rounded-md px-2 py-0.5 text-xs font-semibold capitalize ring-1 ring-inset ${status === "open" ? "bg-surface text-muted ring-line" : "bg-mist text-navy ring-line-strong"}`}>
                Status: {status}
              </span>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:flex sm:flex-wrap">
              <div><dt className="text-xs text-subtle">Probability</dt><dd className="font-semibold tabular-nums">{prob(detail.probability)}</dd></div>
              <div><dt className="text-xs text-subtle">Money at risk</dt><dd className="font-semibold tabular-nums">{money(detail.amount_at_risk, currency)}</dd></div>
              <div><dt className="text-xs text-subtle">Accounts</dt><dd className="font-semibold tabular-nums">{detail.accounts}</dd></div>
              <div><dt className="text-xs text-subtle">Alerts</dt><dd className="font-semibold tabular-nums">{detail.transactions}</dd></div>
              <div className="col-span-2"><dt className="text-xs text-subtle">Opened</dt><dd className="font-semibold">{time(detail.opened_at)}</dd></div>
            </dl>
          </div>
          <div className="no-print flex w-full flex-col gap-2 sm:w-auto">
            <span className="text-xs font-semibold text-muted">Review decision</span>
            <div className="grid grid-cols-2 gap-2 sm:flex">
              <Button variant="secondary" onClick={() => setAsking("confirmed")} disabled={decision !== null}>
                <Icon name="check" className="h-4 w-4" /> Confirm fraud
              </Button>
              <Button variant="secondary" onClick={() => setAsking("dismissed")} disabled={decision !== null}>
                <Icon name="x" className="h-4 w-4" /> Dismiss
              </Button>
            </div>
          </div>
        </div>
        {decision && <Notice tone="success" className="mt-4" title="Decision recorded">{decision.message} No account has been frozen and no report has been filed.</Notice>}
        {decisionError && <div className="mt-4"><ErrorNote title="Decision not recorded" error={decisionError} /></div>}

        <nav aria-label="Case sections" className="no-print mt-5 -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <ul className="flex gap-1 whitespace-nowrap border-b border-line">
            {SECTIONS.map(([anchor, label]) => (
              <li key={anchor}>
                <a href={`#${anchor}`} className="inline-flex min-h-11 items-center border-b-2 border-transparent px-3 text-sm font-medium text-muted hover:border-line-strong hover:text-ink">{label}</a>
              </li>
            ))}
          </ul>
        </nav>
      </div>

      {/* 2. Recovery metrics */}
      <RecoveryMetrics plan={plan} currency={currency} />

      {/* 3. Evidence */}
      <Card id="evidence" title="Why Ripple flagged it" className="scroll-mt-20"
            description="Each statement cites the payments behind it and what would have kept it from firing.">
        {detail.narrative && (
          <div className="mb-4 rounded-lg bg-mist p-3 sm:p-4">
            <p className="text-xs font-semibold text-navy-700">Case summary · AI-drafted, checked against the case facts</p>
            <p className="mt-1 text-[15px] leading-relaxed text-ink">{detail.narrative}</p>
          </div>
        )}
        <EvidenceList reasons={detail.reasons} />
        <div className="mt-4 space-y-2">
          <AccountProfiles profiles={detail.profiles} currency={currency} />
          <ModelContributions shap={detail.shap} />
        </div>
      </Card>

      {/* 4. Money flow */}
      <Card id="money-flow" title="Follow the money" className="scroll-mt-20"
            description={`${edges.length} payments across ${detail.nodes.length} accounts, left to right by hop.`}>
        <div className="space-y-3">
          <ReplayControls edges={edges} step={step} onStep={setStep} />
          <MoneyGraph edges={edges} accounts={accounts} frozen={plan.freeze.map((f) => f.account_id)} upTo={at} currency={currency} />
        </div>
      </Card>

      {/* 5. Recovery over time */}
      <div id="recovery" className="scroll-mt-20">
        <RecoveryChart plan={plan} currency={currency} />
      </div>

      {/* 6. Freeze plan */}
      <div id="freeze-plan" className="scroll-mt-20">
        <FreezeList plan={plan} currency={currency} />
      </div>

      {/* 7. Timeline */}
      <Card id="timeline" title="Case timeline" className="scroll-mt-20" description="Payments and audit-relevant events, oldest first.">
        <Timeline transactions={detail.timeline} events={events} />
      </Card>

      <DecisionDialog verdict={asking} caseId={detail.case_id} busy={deciding} onCancel={() => setAsking(null)} onConfirm={decide} />
    </div>
  );
}
