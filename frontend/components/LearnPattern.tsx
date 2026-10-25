"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, Card, EmptyState, ErrorNote, Icon, Notice, Spinner } from "@/components/ui";
import { api, pct, time, type LearnedPattern, type LearnRequest } from "@/lib/api";

/** How common a rule is among ordinary relay payments on its own. Rare rules are what make the pattern safe. */
function Rarity({ share }: { share: number }) {
  const label = share < 0.001 ? "under 0.1%" : pct(share, share < 0.1 ? 1 : 0);
  return (
    <div className="flex items-center gap-2" title={`${label} of ordinary relay payments meet this rule on its own`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-sunken" aria-hidden>
        <div className="h-full rounded-full bg-teal" style={{ width: `${Math.max(share * 100, 2)}%` }} />
      </div>
      <span className="w-20 text-right text-xs tabular-nums text-muted">{label}</span>
    </div>
  );
}

export function PatternCard({ pattern, onChange }: { pattern: LearnedPattern; onChange?: (p: LearnedPattern) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSteps, setShowSteps] = useState(false);

  const toggle = async () => {
    setBusy(true);
    setError(null);
    try {
      onChange?.(await (pattern.deployed ? api.retire(pattern.motif_id) : api.deploy(pattern.motif_id)));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-subtle">Learned pattern {pattern.motif_id}</p>
          <h3 className="text-lg font-semibold text-navy">{pattern.name}</h3>
          <p className="text-sm text-muted">Learned from {pattern.learned_from}, {time(pattern.learned_at)}.</p>
        </div>
        <div className="flex items-center gap-2">
          {pattern.deployed && (
            <span className="inline-flex items-center gap-1 rounded-md bg-teal-soft px-2 py-0.5 text-xs font-semibold text-teal-strong ring-1 ring-inset ring-teal">
              <Icon name="activity" className="h-3.5 w-3.5" /> Live · {pattern.hits} match{pattern.hits === 1 ? "" : "es"}
            </span>
          )}
          <Button variant={pattern.deployed ? "secondary" : "primary"} onClick={toggle} disabled={busy}>
            {busy ? <Spinner /> : <Icon name={pattern.deployed ? "pause" : "shield"} className="h-4 w-4" />}
            {pattern.deployed ? "Retire" : "Deploy as a live detector"}
          </Button>
        </div>
      </div>

      <div>
        <p className="text-sm font-semibold text-ink">A payment matches when all of these hold</p>
        <ul className="mt-2 divide-y divide-line rounded-md border border-line">
          {pattern.rules.map((r) => (
            <li key={r.feature} className="flex flex-col gap-1 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="text-sm text-ink">{r.text}</span>
              <Rarity share={r.background_share} />
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-subtle">The bar shows how many ordinary relay payments meet each rule on its own. Together they are rarer still.</p>
      </div>

      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-md bg-mist p-3">
          <dt className="text-xs text-muted">Expected false alarms</dt>
          <dd className="text-lg font-semibold tabular-nums text-navy">{pattern.false_alarms_per_day.toFixed(2)} a day</dd>
          <dd className="text-xs text-subtle">{pattern.background_matches} of {pattern.background_events.toLocaleString("en-IN")} ordinary payments in {pattern.background_days} days</dd>
        </div>
        <div className="rounded-md bg-mist p-3">
          <dt className="text-xs text-muted">Earliest warning on the example</dt>
          <dd className="text-lg font-semibold tabular-nums text-navy">{pattern.lead_hours != null ? `${pattern.lead_hours} h` : "—"}</dd>
          <dd className="text-xs text-subtle">before the last of the money was cashed out</dd>
        </div>
        <div className="rounded-md bg-mist p-3">
          <dt className="text-xs text-muted">Learned from</dt>
          <dd className="text-lg font-semibold tabular-nums text-navy">1 trail</dd>
          <dd className="text-xs text-subtle">{pattern.example_txn_ids.length} payments, no labels needed</dd>
        </div>
      </dl>

      {pattern.steps.length > 0 && (
        <div>
          <button type="button" onClick={() => setShowSteps(!showSteps)} aria-expanded={showSteps}
                  className="flex min-h-9 items-center gap-1 rounded px-1 text-sm font-semibold text-link hover:bg-mist">
            <Icon name="chevron" className={`h-4 w-4 transition-transform ${showSteps ? "rotate-180" : ""}`} />
            How Ripple generalised the example ({pattern.steps.length} steps)
          </button>
          {showSteps && (
            <ol className="mt-2 list-decimal space-y-1 pl-6 text-sm text-muted">
              {pattern.steps.map((s) => <li key={s}>{s}</li>)}
            </ol>
          )}
        </div>
      )}

      {error && <ErrorNote title="Could not change the pattern" error={error} />}
      {pattern.deployed && (
        <Notice tone="success" title="Live on every payment">
          A match counts as pattern-detector evidence, so it goes through the same scoring, cases, hold plans and feedback as the built-in detectors.
        </Notice>
      )}
    </div>
  );
}

/** "Teach Ripple this pattern": learns from the trail just traced or the case being reviewed. */
export function LearnFromTrail({ request, what }: { request: LearnRequest; what: string }) {
  const [pattern, setPattern] = useState<LearnedPattern | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const learn = async () => {
    setBusy(true);
    setError(null);
    try {
      setPattern(await api.learn(request));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Teach Ripple this pattern"
          description={`If no detector caught ${what}, Ripple can learn its shape from this one trail and check it against the bank's last 30 days before anything goes live.`}>
      {!pattern ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Button variant="primary" size="lg" onClick={learn} disabled={busy}>
            {busy ? <><Spinner /> Learning from one example…</> : <><Icon name="flask" className="h-5 w-5" /> Learn this pattern</>}
          </Button>
          <p className="text-xs text-subtle">Learning reads payments only. Nothing changes until an officer deploys the pattern.</p>
        </div>
      ) : (
        <PatternCard pattern={pattern} onChange={setPattern} />
      )}
      {error && <div className="mt-4"><ErrorNote title="Could not learn a pattern" error={error} /></div>}
    </Card>
  );
}

/** Command-centre panel: every learned pattern and its live matches. */
export function LearnedPatterns() {
  const [patterns, setPatterns] = useState<LearnedPattern[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.motifs().then((p) => { setPatterns(p); setError(null); }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <Card title="Learned patterns"
          description="Detectors Ripple learned from one confirmed trail each. Report a scam the queue missed, then teach Ripple its shape.">
      {error ? (
        <ErrorNote title="Could not load learned patterns" error={error} onRetry={load} />
      ) : patterns === null ? (
        <p className="flex items-center gap-2 text-sm text-muted" role="status"><Spinner /> Loading…</p>
      ) : patterns.length === 0 ? (
        <EmptyState icon="flask" title="No learned patterns yet">
          After a trace, choose <span className="font-semibold">Learn this pattern</span>. <Link href="/trace" className="font-semibold text-link underline">Report a scam</Link>
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line">
          {patterns.map((p) => (
            <li key={p.motif_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className="font-mono text-xs font-semibold text-muted">{p.motif_id}</span>
              <span className="min-w-0 flex-1 text-sm font-semibold text-ink">{p.name}</span>
              <span className="text-xs tabular-nums text-muted">{p.false_alarms_per_day.toFixed(2)} false alarms a day expected</span>
              <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${p.deployed ? "bg-teal-soft text-teal-strong" : "bg-sunken text-muted"}`}>
                {p.deployed ? `Live · ${p.hits} match${p.hits === 1 ? "" : "es"}` : "Not deployed"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
