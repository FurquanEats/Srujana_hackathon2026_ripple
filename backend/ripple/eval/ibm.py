"""IBM AML evaluation: replay, train LightGBM on a time split, and write data/eval.json.

    python -m ripple.eval.ibm --data ../data/processed/ibm_hi_small.parquet --out ../data/eval.json

1. Replay every row through the live engine (ibm_aml pack, no model) and keep, per row, the detector, baseline and
   graph layer scores plus the exact feature row the engine built (via Engine.on_features).
2. Split by day: the first 70% of days train, the rest test. LightGBM learns from the training days; its last 15%
   of days calibrate it (isotonic). The model is saved for the engine's model layer.
3. On the test days, fuse layer scores the way the engine does and report precision and recall at the alert
   threshold, PR-AUC, precision in the top 50, an ablation (one layer added at a time), results per IBM pattern,
   and the alert-budget curve (top-k alerts per day).

Rows the engine never alerts on (warm-up and transfers to the same account) are left out of every metric.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ripple.engine import Engine
from ripple.fusion import QUIET
from ripple.schema import EvalReport, Layer, Rail, Transaction

TRAIN_SHARE = 0.7
CALIB_SHARE = 0.15  # of training days, the latest ones
COLD_HOURS = 48
NEG_SAMPLE = 0.10  # share of legitimate rows used for training
TAIL_SHARE = 0.01  # a day with fewer rows than this share of the busiest day is tail, not a full day
BUDGETS = [10, 25, 50, 100, 200, 500, 1000, 2000]
# The Ripple detector aimed at each IBM pattern; bipartite, stack and random have none.
DETECTOR_FOR = {"fan_in": "fan_in_out", "fan_out": "fan_out_burst", "cycle": "temporal_cycle",
                "scatter_gather": "scatter_gather", "gather_scatter": "fan_in_out"}
SINGLE_TXN =["log_amount", "hour", "is_cash"]  # what a rule on one transaction alone can see
LGB_PARAMS = {"objective": "binary", "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 50,
              "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 7}


def replay(df: pd.DataFrame, pack: str = "ibm_aml", log_every: int = 250_000) -> dict:
    """Runs the engine over df (sorted by ts) and returns per-row layer scores, features and a scored flag."""
    n = len(df)
    layers = np.zeros((n, 3), dtype=np.float32)  # detector, baseline, graph
    scored = np.zeros(n, dtype=bool)
    feats: np.ndarray | None = None
    names: list[str] = []
    row = 0

    def capture(txn: Transaction, features: dict[str, float]) -> None:
        nonlocal feats, names
        if feats is None:
            names = list(features)
            feats = np.zeros((n, len(names)), dtype=np.float32)
        feats[row] = [features[k] for k in names]

    engine = Engine(pack, on_features=capture)
    rails = {r.value: r for r in Rail}
    started = time.perf_counter()
    cols = zip(df["txn_id"], df["ts"], df["src_account"], df["dst_account"], df["amount"], df["rail"])
    for row, (txn_id, ts, src, dst, amount, rail) in enumerate(cols):
        txn = Transaction.model_construct(txn_id=txn_id, ts=ts.to_pydatetime(), src_account=src, dst_account=dst,
                                          amount=float(amount), currency="USD", rail=rails[rail], src_handle=None,
                                          device_id=None, location=None, channel=None)
        result, _ = engine.process(txn)
        s = result.layer_scores
        layers[row] = (s[Layer.DETECTOR], s[Layer.BASELINE], s[Layer.GRAPH])
        scored[row] = src != dst and not engine.warming_up(txn.ts)
        if log_every and (row + 1) % log_every == 0:
            elapsed = time.perf_counter() - started
            print(f"  replayed {row + 1:,} rows in {elapsed:,.0f}s ({(row + 1) / elapsed:,.0f}/s)", flush=True)
    stats = engine.stats()
    return {"layers": layers, "scored": scored, "features": feats, "names": names, "fusion": engine.fusion,
            "alert_at": engine.alert_at, "tps": n / (time.perf_counter() - started),
            "p95_latency_ms": stats["p95_latency_ms"]}


def fuse(fusion, det, base, graph, model) -> np.ndarray:
    """Vectorised Fusion.probability, including the baseline-only cap."""
    w = fusion.weights
    x = fusion.bias + w[Layer.DETECTOR] * det + w[Layer.BASELINE] * base + w[Layer.GRAPH] * graph + w[Layer.MODEL] * model
    p = 1 / (1 + np.exp(-x))
    others = np.maximum.reduce([det, graph, model])
    return np.where(others < QUIET, np.minimum(p, fusion.baseline_only_cap), p)


def train_lgbm(X: np.ndarray, y: np.ndarray, fit_mask: np.ndarray, calib_mask: np.ndarray, names: list[str]):
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression

    from ripple.models.lgbm import LightGBMModel

    pos = y[fit_mask].sum()
    params = LGB_PARAMS | {"scale_pos_weight": min(50.0, (fit_mask.sum() - pos) / max(pos, 1))}
    booster = lgb.train(params, lgb.Dataset(X[fit_mask], y[fit_mask], feature_name=names), num_boost_round=300)
    raw = booster.predict(X[calib_mask])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(raw, y[calib_mask])
    return LightGBMModel(booster, names, list(iso.X_thresholds_), list(iso.y_thresholds_))


def metrics(name: str, p: np.ndarray, y: np.ndarray, alert_at: float | None = None, top_alerts: int | None = None):
    """Precision and recall either at a probability threshold or for the top_alerts highest probabilities."""
    from sklearn.metrics import average_precision_score

    if top_alerts is not None:
        alert = np.zeros(len(p), dtype=bool)
        alert[np.argsort(-p, kind="stable")[:top_alerts]] = True
    else:
        alert = p >= alert_at
    tp = int((alert & (y == 1)).sum())
    top50 = np.argsort(-p, kind="stable")[:50]
    return {"name": name, "precision": round(tp / max(int(alert.sum()), 1), 4), "recall": round(tp / max(int(y.sum()), 1), 4),
            "pr_auc": round(float(average_precision_score(y, p)), 4) if y.any() else None,
            "precision_at_50": round(float(y[top50].mean()), 4)}


def budget_curve(p: np.ndarray, y: np.ndarray, amount: np.ndarray, day: np.ndarray) -> list[dict]:
    points = []
    order = np.lexsort((-p, day))  # by day, then highest probability first
    rank = np.empty(len(p), dtype=np.int64)
    day_sorted = day[order]
    starts = np.r_[0, np.flatnonzero(np.diff(day_sorted)) + 1]
    pos_in_day = np.arange(len(p)) - np.repeat(starts, np.diff(np.r_[starts, len(p)]))
    rank[order] = pos_in_day
    value = (amount * y).sum()
    for k in BUDGETS:
        alert = rank < k
        tp = (alert & (y == 1))
        points.append({"alerts_per_day": k, "recall": round(float(tp.sum() / max(y.sum(), 1)), 4),
                       "precision": round(float(tp.sum() / max(alert.sum(), 1)), 4),
                       "value_caught_share": round(float((amount * tp).sum() / value), 4) if value else 0.0})
    return points


def recoverable_at_first_alert(name: str, attempts: pd.DataFrame, alert: np.ndarray) -> dict:
    """Per laundering attempt (attempt_id >= 0): share of its money in transactions at or after its first alert.
    An attempt that is never alerted recovers nothing."""
    a = attempts.assign(alert=alert)
    a = a[a["attempt_id"] >= 0]
    shares = []
    for _, g in a.groupby("attempt_id"):
        hit = g.loc[g["alert"], "ts"]
        if hit.empty:
            shares.append(0.0)
        else:
            shares.append(float(g.loc[g["ts"] >= hit.min(), "amount"].sum() / g["amount"].sum()))
    shares = np.array(shares)
    alerted = a.groupby("attempt_id")["alert"].any()
    return {"name": name, "attempts": len(shares), "alerted_share": round(float(alerted.mean()), 4) if len(shares) else 0.0,
            "median_recoverable": round(float(np.median(shares)), 4) if len(shares) else 0.0,
            "mean_recoverable": round(float(shares.mean()), 4) if len(shares) else 0.0}


def run(data: Path, out: Path, model_out: Path | None, rows: int | None) -> dict:
    t0 = time.perf_counter()
    df = pd.read_parquet(data)
    if rows:
        df = df.iloc[:rows]
    print(f"{len(df):,} rows loaded in {time.perf_counter() - t0:.0f}s; replaying...", flush=True)
    r = replay(df)
    y = df["is_laundering"].to_numpy(dtype=np.int8)
    day = df["ts"].dt.floor("D").to_numpy()
    days, per_day = np.unique(day, return_counts=True)
    # HI-Small ends with a tail of near-empty days that are mostly laundering (Sep 11-18: a few hundred rows a day
    # against 200,000+ before). Splitting there would leave a tiny, almost all-positive test set, so only full days
    # count; the tail is replayed (the engine needs the history) but left out of training and testing.
    full_days = days[per_day >= TAIL_SHARE * per_day.max()]
    tail = len(days) - len(full_days)
    days = full_days
    n_train = max(1, math.ceil(TRAIN_SHARE * len(days)))
    n_calib = max(1, math.ceil(CALIB_SHARE * n_train))
    train_days, test_days = days[:n_train], days[n_train:]
    in_train, in_test = np.isin(day, train_days), np.isin(day, test_days)
    in_calib = np.isin(day, train_days[-n_calib:])
    scored = r["scored"]
    X, names = r["features"], r["names"]
    # Training leaves out the first COLD_HOURS (features there are cold-start noise) and keeps every positive but
    # only a seeded share of negatives. Testing always uses every row.
    warm = df["ts"].to_numpy() >= df["ts"].iloc[0] + pd.Timedelta(hours=COLD_HOURS)
    keep = (y == 1) | (np.random.default_rng(7).random(len(y)) < NEG_SAMPLE)
    in_train &= warm & keep
    in_calib &= warm & keep

    print(f"training on {len(train_days)} days ({(in_train & scored).sum():,} rows), "
          f"testing on {len(test_days)} days ({(in_test & scored).sum():,} rows)", flush=True)
    full = train_lgbm(X, y, in_train & ~in_calib & scored, in_calib & scored, names)
    single_idx = [names.index(f) for f in SINGLE_TXN]
    single = train_lgbm(X[:, single_idx], y, in_train & ~in_calib & scored, in_calib & scored, SINGLE_TXN)
    if model_out:
        full.save(model_out, {"trained_on": str(data), "train_days": [str(d)[:10] for d in train_days]})

    test = in_test & scored
    yt = y[test]
    det, base, graph = (r["layers"][test, i].astype(float) for i in range(3))
    model_p = full.predict(X[test])
    zero = np.zeros_like(det)
    fusion, alert_at = r["fusion"], r["alert_at"]
    variants = {
        "Detectors only": fuse(fusion, det, zero, zero, zero),
        "+ behavioural baseline": fuse(fusion, det, base, zero, zero),
        "+ graph layer": fuse(fusion, det, base, graph, zero),
        "+ calibrated LightGBM": fuse(fusion, det, base, graph, model_p),
    }
    p_full = variants["+ calibrated LightGBM"]
    n_alerts = int((p_full >= alert_at).sum())
    # The single-transaction baseline gets the same number of alerts as the full system, so the two compare fairly.
    p_single = single.predict(X[test][:, single_idx])
    baseline = metrics("Single-transaction baseline", p_single, yt, top_alerts=n_alerts)
    ablation = [baseline] + [metrics(k, v, yt, alert_at) for k, v in variants.items()]
    overall = metrics("Ripple (full)", p_full, yt, alert_at)

    patterns = df.loc[test, "pattern"].to_numpy()
    alert = p_full >= alert_at
    per_typology = []
    for pat in sorted(set(patterns[yt == 1])):
        is_pat = (patterns == pat) & (yt == 1)
        keep = is_pat | (yt == 0)  # this pattern's rows against every legitimate row
        label = f"{pat.replace('_', '-')} ({DETECTOR_FOR.get(pat, 'graph layer and model only')})" if pat else "untagged"
        m = metrics(label, p_full[keep], is_pat[keep].astype(np.int8), alert_at)
        m["recall"] = round(float((alert & is_pat).sum() / is_pat.sum()), 4)
        per_typology.append(m | {"precision_at_50": None})

    curve = budget_curve(p_full, yt, df.loc[test, "amount"].to_numpy(), day[test])
    single_alert = np.zeros(len(p_single), dtype=bool)
    single_alert[np.argsort(-p_single, kind="stable")[:n_alerts]] = True
    attempts = df.loc[test, ["attempt_id", "ts", "amount"]].reset_index(drop=True)
    recoverable = [recoverable_at_first_alert("Ripple (full)", attempts, alert),
                   recoverable_at_first_alert("Single-transaction baseline", attempts, single_alert)]
    best = max(pt["value_caught_share"] for pt in curve)
    suggested = next(pt["alerts_per_day"] for pt in curve if pt["value_caught_share"] >= 0.9 * best)

    report = {
        "dataset": f"IBM AML {data.stem}",
        "split": f"time split: train on the first {len(train_days)} of {len(days)} days "
                 f"({str(train_days[0])[:10]} to {str(train_days[-1])[:10]}), test on the last {len(test_days)}",
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "overall": overall,
        "baseline": baseline,
        "ablation": ablation,
        "per_typology": per_typology,
        "budget_curve": curve,
        "suggested_budget": suggested,
        "throughput_tps": round(r["tps"], 1),
        "p95_latency_ms": r["p95_latency_ms"],
        "money_recoverable": recoverable,
        "notes": [
            f"Test set: {int(test.sum()):,} transactions, {int(yt.sum()):,} laundering. Warm-up rows and transfers "
            "to the same account are excluded because the engine never alerts on them.",
            f"Alert threshold {alert_at} as in the ibm_aml pack; fusion weights are the pack defaults, not refitted.",
            "The single-transaction baseline is LightGBM on amount, hour and cash only, given as many alerts as the "
            "full system.",
            "Per-pattern precision compares that pattern's laundering rows against all legitimate rows, so it is "
            "lower than overall precision.",
            "Pattern tags come from HI-Small_Patterns.txt; laundering rows not listed there are 'untagged'.",
            f"{tail} near-empty tail days at the end of the dataset (mostly laundering rows) are replayed but not "
            "used for training or testing.",
        ],
    }
    EvalReport.model_validate(report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("overall", "baseline", "suggested_budget", "throughput_tps")}, indent=1))
    print(f"done in {time.perf_counter() - t0:,.0f}s -> {out}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("../data/processed/ibm_hi_small.parquet"))
    parser.add_argument("--out", type=Path, default=Path("../data/eval.json"))
    parser.add_argument("--model-out", type=Path, default=Path("../data/models/ibm_lgbm.txt"))
    parser.add_argument("--rows", type=int, default=None, help="only the first N rows (for a quick check)")
    args = parser.parse_args()
    run(args.data, args.out, args.model_out, args.rows)


if __name__ == "__main__":
    main()
