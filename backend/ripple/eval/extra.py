"""Extra IBM evaluation: a calibration table and precision at the top 50 cases per day.

The alert-level numbers in ripple.eval.ibm rank single transactions. An analyst works a queue of cases, so this module
groups alerts into cases with the live CaseEngine (same linking rule, same tiers) and ranks the cases the way the
queue does: by tier, then expected loss. A case counts as a hit if it contains at least one laundering transaction.
Results go to a sidecar file, not EvalReport, so the shared API contract in schema.py is untouched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ripple.cases import CaseEngine, TIER_ORDER
from ripple.schema import Rail, ScoredTransaction

CAL_EDGES = [0.0, 0.01, 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0000001]
CASES_PER_DAY = 50


def calibration_table(p: np.ndarray, y: np.ndarray) -> dict:
    """Reliability table: mean predicted probability against the observed laundering rate in each bin."""
    bins = np.digitize(p, CAL_EDGES[1:-1])
    rows, ece = [], 0.0
    for b in range(len(CAL_EDGES) - 1):
        m = bins == b
        if not m.any():
            continue
        pred, obs = float(p[m].mean()), float(y[m].mean())
        ece += m.sum() / len(p) * abs(pred - obs)
        rows.append({"bin": f"[{CAL_EDGES[b]:g}, {min(CAL_EDGES[b + 1], 1.0):g})", "rows": int(m.sum()),
                     "mean_predicted": round(pred, 4), "observed_rate": round(obs, 4)})
    return {"bins": rows, "ece": round(float(ece), 5), "brier": round(float(np.mean((p - y) ** 2)), 6)}


def build_cases(test_df: pd.DataFrame, alert: np.ndarray, p: np.ndarray, tiers: dict) -> list[dict]:
    """Runs the alerts through CaseEngine in time order and returns one record per case (final state)."""
    amount_of = dict(zip(test_df["txn_id"], test_df["amount"])).get
    engine = CaseEngine(tiers, amount_of=lambda i: float(amount_of(i, 0.0)))
    rails = {r.value: r for r in Rail}
    cols = zip(test_df["txn_id"], test_df["ts"], test_df["src_account"], test_df["dst_account"], test_df["amount"],
               test_df["rail"], p, test_df["is_laundering"], test_df["attempt_id"], alert)
    label: dict[str, tuple[int, int]] = {}
    for txn_id, ts, src, dst, amount, rail, prob, laundering, attempt, is_alert in cols:
        if not is_alert:
            continue
        t = ScoredTransaction.model_construct(
            txn_id=txn_id, ts=ts.to_pydatetime(), src_account=src, dst_account=dst, amount=float(amount),
            currency="USD", rail=rails[rail], probability=float(prob), confidence=1.0, layer_scores={}, reasons=[],
            is_alert=True, case_id=None)
        engine.add(t)
        label[txn_id] = (int(laundering), int(attempt))
    out = []
    for case in engine.cases.values():
        s = engine.summary(case)
        hits = [label[t.txn_id] for t in case.alerts]
        out.append({"case_id": s.case_id, "tier": s.tier, "expected_loss": s.expected_loss,
                    "opened_day": s.opened_at.date().isoformat(), "alerts": len(hits),
                    "laundering_alerts": sum(h[0] for h in hits),
                    "attempts": {h[1] for h in hits if h[0] and h[1] >= 0}})
    return out


def precision_at_top_cases(cases: list[dict], total_attempts: int, k: int = CASES_PER_DAY) -> dict:
    """Pooled over days: take the first k cases opened each day in queue order (tier, then expected loss)."""
    by_day: dict[str, list[dict]] = {}
    for c in cases:
        by_day.setdefault(c["opened_day"], []).append(c)
    picked, days = [], 0
    for day in sorted(by_day):
        ranked = sorted(by_day[day], key=lambda c: (TIER_ORDER[c["tier"]], -c["expected_loss"]))
        if len(ranked) >= k:  # a day with fewer cases than the budget says nothing about the budget
            days += 1
            picked.extend(ranked[:k])
    hit = [c for c in picked if c["laundering_alerts"] > 0]
    attempts = set().union(*(c["attempts"] for c in picked)) if picked else set()
    return {
        "cases_per_day": k, "days": days, "cases_reviewed": len(picked),
        "precision_any_laundering": round(len(hit) / len(picked), 4) if picked else None,
        "precision_majority_laundering": round(
            sum(c["laundering_alerts"] * 2 >= c["alerts"] for c in picked) / len(picked), 4) if picked else None,
        "attempts_touched": len(attempts), "attempts_in_test": total_attempts,
    }


def case_level_report(name: str, test_df: pd.DataFrame, alert: np.ndarray, p: np.ndarray, tiers: dict) -> dict:
    cases = build_cases(test_df, alert, p, tiers)
    total_attempts = int(test_df.loc[test_df["attempt_id"] >= 0, "attempt_id"].nunique())
    return {
        "name": name,
        "alerts": int(alert.sum()),
        "cases": len(cases),
        "cases_with_laundering": sum(c["laundering_alerts"] > 0 for c in cases),
        "alerts_per_case_median": float(np.median([c["alerts"] for c in cases])) if cases else 0.0,
        **precision_at_top_cases(cases, total_attempts),
    }
