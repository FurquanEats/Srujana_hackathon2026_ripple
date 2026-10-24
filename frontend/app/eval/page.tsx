"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, ErrorNote, Stat } from "@/components/ui";
import { api, pct, type ConsortiumReport, type EvalReport } from "@/lib/api";

const tooltip = { contentStyle: { background: "#0f172a", border: "1px solid #334155" } };

export default function Evaluation() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consortium, setConsortium] = useState<ConsortiumReport | null>(null);

  useEffect(() => {
    api.eval().then(setReport).catch((e) => setError(e.message));
    api.consortium().then(setConsortium).catch(() => setConsortium(null));
  }, []);

  if (error) return <ErrorNote error={error} />;
  if (!report) return <p className="text-slate-400">Loading evaluation…</p>;

  const o = report.overall;
  const b = report.baseline;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Evaluation</h1>
        <p className="text-sm text-slate-400">{report.dataset} · {report.split}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Precision" value={pct(o.precision)} hint={`single-transaction rule ${pct(b.precision)}`} />
        <Stat label="Recall" value={pct(o.recall)} hint={`single-transaction rule ${pct(b.recall)}`} />
        <Stat label="PR-AUC" value={o.pr_auc != null ? o.pr_auc.toFixed(2) : "n/a"} hint={b.pr_auc != null ? `rule ${b.pr_auc.toFixed(2)}` : undefined} />
        <Stat label="Throughput" value={report.throughput_tps ? `${Math.round(report.throughput_tps).toLocaleString("en-IN")}/s` : "n/a"}
              hint={report.p95_latency_ms ? `p95 ${report.p95_latency_ms} ms per payment` : undefined} />
      </div>

      {report.money_recoverable && report.money_recoverable.length > 0 && (
        <Card title="Money still recoverable when the system first alerts">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr><th className="py-2">System</th><th className="text-right">Attempts</th><th className="text-right">Alerted</th><th className="text-right">Median recoverable</th><th className="text-right">Mean recoverable</th></tr>
            </thead>
            <tbody>
              {report.money_recoverable.map((r) => (
                <tr key={r.name} className="border-t border-slate-800">
                  <td className="py-2">{r.name}</td>
                  <td className="text-right tabular-nums">{r.attempts}</td>
                  <td className="text-right tabular-nums">{pct(r.alerted_share)}</td>
                  <td className="text-right tabular-nums">{pct(r.median_recoverable)}</td>
                  <td className="text-right tabular-nums">{pct(r.mean_recoverable)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="What each layer adds (ablation)">
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={report.ablation} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid stroke="#1e293b" />
                <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => pct(v)} stroke="#64748b" fontSize={11} />
                <YAxis type="category" dataKey="name" width={170} stroke="#64748b" fontSize={11} />
                <Tooltip formatter={(v) => pct(Number(v), 1)} {...tooltip} />
                <Legend />
                <Bar dataKey="precision" name="Precision" fill="#38bdf8" />
                <Bar dataKey="recall" name="Recall" fill="#34d399" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title={`Alert budget (suggested: ${report.suggested_budget} a day)`}>
          <div className="h-72">
            <ResponsiveContainer>
              <LineChart data={report.budget_curve}>
                <CartesianGrid stroke="#1e293b" />
                <XAxis dataKey="alerts_per_day" type="number" domain={["dataMin", "dataMax"]} stroke="#64748b" fontSize={11} label={{ value: "alerts per day", position: "insideBottom", offset: -2, fill: "#64748b", fontSize: 11 }} />
                <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v)} stroke="#64748b" fontSize={11} />
                <Tooltip formatter={(v) => pct(Number(v), 1)} {...tooltip} />
                <Legend />
                <Line dataKey="recall" name="Laundering caught" stroke="#34d399" dot={false} />
                <Line dataKey="value_caught_share" name="Value caught" stroke="#fbbf24" dot={false} />
                <Line dataKey="precision" name="Precision" stroke="#38bdf8" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {consortium && (
        <Card title={`Bank consortium: ${consortium.member_banks.length} banks sharing only keyed hashes`}>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr><th className="py-2">Mode</th><th className="text-right">Laundering payments</th><th className="text-right">Caught</th><th className="text-right">Recall</th><th className="text-right">Alerts</th><th className="text-right">Precision</th></tr>
            </thead>
            <tbody>
              {consortium.results.map((r) => (
                <tr key={r.mode} className="border-t border-slate-800">
                  <td className="py-2">{r.mode}</td>
                  <td className="text-right tabular-nums">{r.laundering_payments}</td>
                  <td className="text-right tabular-nums">{r.caught}</td>
                  <td className="text-right tabular-nums">{r.recall != null ? pct(r.recall, 1) : "n/a"}</td>
                  <td className="text-right tabular-nums">{r.alerts}</td>
                  <td className="text-right tabular-nums">{r.precision != null ? pct(r.precision, 1) : "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">{consortium.dataset}, {consortium.rows.toLocaleString("en-IN")} payments. {consortium.note}</p>
        </Card>
      )}

      <Card title="By laundering pattern">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500"><tr><th className="py-2">Pattern (detector aimed at it)</th><th className="text-right">Precision</th><th className="text-right">Recall</th></tr></thead>
          <tbody>
            {report.per_typology.map((r) => (
              <tr key={r.name} className="border-t border-slate-800">
                <td className="py-2">{r.name}</td>
                <td className="text-right tabular-nums">{pct(r.precision)}</td>
                <td className="text-right tabular-nums">{pct(r.recall)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {report.notes.length > 0 && (
        <Card title="Notes and limits">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-400">{report.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </Card>
      )}
    </div>
  );
}
