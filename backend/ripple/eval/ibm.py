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
from ripple.eval.extra import calibration_table, case_level_report
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
            "alert_at": engine.alert_at, "tiers": engine.pack["tiers"], "tps": n / (time.perf_counter() - started),
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


def save_replay(r: dict, cache: Path) -> None:
    """Stores a replay so the evaluation can be rerun without the 40-minute engine pass. The fusion object is not
    stored: replay never changes it, so a fresh Engine of the same pack has identical weights."""
    cache.mkdir(parents=True, exist_ok=True)
    np.savez(cache / "replay.npz", layers=r["layers"], scored=r["scored"], features=r["features"])
    scalars = {k: r[k] for k in ("names", "alert_at", "tiers", "tps", "p95_latency_ms")}
    (cache / "replay.json").write_text(json.dumps(scalars))


def load_replay(cache: Path, rows: int | None, pack: str = "ibm_aml") -> dict | None:
    if not (cache / "replay.npz").exists() or rows:
        return None
    z = np.load(cache / "replay.npz")
    meta = json.loads((cache / "replay.json").read_text())
    return {"layers": z["layers"], "scored": z["scored"], "features": z["features"], "fusion": Engine(pack).fusion,
            **meta}


def calibrate_fused(p_cal: np.ndarray, y_cal: np.ndarray, p_test: np.ndarray, fallback: float) -> dict:
    """Platt scaling of a fused probability, fitted on held-out unsampled rows, plus the F1-best alert threshold.

    Logistic calibration keeps the ranking (it is monotone and strictly increasing), unlike isotonic steps which tie.
    The threshold is chosen on the same held-out rows, never on the test days."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import precision_recall_curve

    def logit(p):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p))

    if y_cal.sum() == 0 or y_cal.sum() == len(y_cal):
        return {"p": p_test, "threshold": fallback, "a": 1.0, "b": 0.0}
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(logit(p_cal)[:, None], y_cal)
    a, b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    p_c = lr.predict_proba(logit(p_cal)[:, None])[:, 1]
    precision, recall, thr = precision_recall_curve(y_cal, p_c)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    return {"p": lr.predict_proba(logit(p_test)[:, None])[:, 1], "threshold": float(thr[int(np.argmax(f1))]),
            "a": a, "b": b}


def run(data: Path, out: Path, model_out: Path | None, rows: int | None, cache: Path | None = None) -> dict:
    t0 = time.perf_counter()
    df = pd.read_parquet(data)
    if rows:
        df = df.iloc[:rows]
    r = load_replay(cache, rows) if cache else None
    if r is None:
        print(f"{len(df):,} rows loaded in {time.perf_counter() - t0:.0f}s; replaying...", flush=True)
        r = replay(df)
        if cache and not rows:
            save_replay(r, cache)
    else:
        print(f"{len(df):,} rows loaded; replay taken from cache {cache}", flush=True)
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
    # Calibration rows are NOT negative-sampled. The model was fitted on 10% of legitimate rows, so any calibrator
    # fitted on the same thinned rows learns a base rate about 10 times too high. The last two training days are held
    # out of fitting: the first calibrates the model (isotonic), the second calibrates the fused probability and
    # picks the alert threshold, so no step is tuned on rows it also learned from.
    calib_days = train_days[-n_calib:]
    in_model_cal = np.isin(day, calib_days[:1]) & warm
    in_fuse_cal = np.isin(day, calib_days[-1:]) & warm
    in_fit = in_train & warm & keep & ~np.isin(day, calib_days)

    print(f"training on {len(train_days) - len(calib_days)} days ({(in_fit & scored).sum():,} rows), calibrating on "
          f"{len(calib_days)} held-out day(s), testing on {len(test_days)} days ({(in_test & scored).sum():,} rows)",
          flush=True)
    full = train_lgbm(X, y, in_fit & scored, in_model_cal & scored, names)
    single_idx = [names.index(f) for f in SINGLE_TXN]
    single = train_lgbm(X[:, single_idx], y, in_fit & scored, in_model_cal & scored, SINGLE_TXN)
    if model_out:
        full.save(model_out, {"trained_on": str(data), "train_days": [str(d)[:10] for d in train_days]})

    test, fuse_cal = in_test & scored, in_fuse_cal & scored
    yt, yc = y[test], y[fuse_cal]

    def layer_scores(mask):
        det, base, graph = (r["layers"][mask, i].astype(float) for i in range(3))
        return det, base, graph, full.predict(X[mask])

    fusion, alert_at = r["fusion"], r["alert_at"]

    def variant_probs(mask):
        det, base, graph, model_p = layer_scores(mask)
        zero = np.zeros_like(det)
        return {
            "Detectors only": fuse(fusion, det, zero, zero, zero),
            "+ behavioural baseline": fuse(fusion, det, base, zero, zero),
            "+ graph layer": fuse(fusion, det, base, graph, zero),
            "+ calibrated LightGBM": fuse(fusion, det, base, graph, model_p),
        }

    raw_test, raw_cal = variant_probs(test), variant_probs(fuse_cal)
    tuned = {k: calibrate_fused(raw_cal[k], yc, raw_test[k], alert_at) for k in raw_test}
    variants = {k: tuned[k]["p"] for k in tuned}
    thresholds = {k: tuned[k]["threshold"] for k in tuned}
    p_full, alert_at_full = variants["+ calibrated LightGBM"], thresholds["+ calibrated LightGBM"]
    n_alerts = int((p_full >= alert_at_full).sum())
    # The single-transaction baseline gets the same number of alerts as the full system, so the two compare fairly.
    p_single = single.predict(X[test][:, single_idx])
    baseline = metrics("Single-transaction baseline", p_single, yt, top_alerts=n_alerts)
    ablation = [baseline] + [metrics(k, v, yt, thresholds[k]) for k, v in variants.items()]
    overall = metrics("Ripple (full)", p_full, yt, alert_at_full)
    alert_at = alert_at_full

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
            f"Alert threshold {alert_at:.4f} is the F1-best threshold on a held-out training day, after Platt scaling of "
            "the fused probability on that day. Fusion weights are the pack defaults, not refitted. The LightGBM model "
            "is isotonic-calibrated on a separate unsampled day, so legitimate-row subsampling does not inflate it.",
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

    # Calibration and case-level precision go to a sidecar file; EvalReport (schema.py) is the shared API contract.
    test_df = df.loc[test, ["txn_id", "ts", "src_account", "dst_account", "amount", "rail", "is_laundering",
                            "attempt_id", "pattern"]].reset_index(drop=True)
    test_df.assign(p_full=p_full, p_single=p_single).to_parquet(out.with_name("ibm_test_scores.parquet"))
    extra = {
        "tuning": {
            "model_calibration_day": str(calib_days[0])[:10], "fusion_calibration_day": str(calib_days[-1])[:10],
            "variants": {k: {"threshold": round(thresholds[k], 5), "platt_a": round(tuned[k]["a"], 4),
                             "platt_b": round(tuned[k]["b"], 4)} for k in tuned},
            "alert_rate_test": round(float((p_full >= alert_at).mean()), 5),
            "pack_alert_at": r["alert_at"],
        },
        "calibration": calibration_table(p_full, yt.astype(float)),
        "calibration_single_transaction": calibration_table(p_single, yt.astype(float)),
        "case_level": [
            case_level_report("Ripple (full)", test_df, alert, p_full, r["tiers"]),
            case_level_report("Single-transaction baseline", test_df, single_alert, p_single, r["tiers"]),
        ],
        "notes": [
            "A case is a hit if it holds at least one laundering transaction. Cases are formed by the live CaseEngine "
            "and ranked by tier then expected loss; the top 50 cases opened each full test day are reviewed.",
            "Days with fewer than 50 cases are skipped.",
        ],
    }
    out.with_name("eval_extra.json").write_text(json.dumps(extra, indent=2, default=str))
    print(json.dumps({k: report[k] for k in ("overall", "baseline", "suggested_budget", "throughput_tps")}, indent=1))
    print(f"done in {time.perf_counter() - t0:,.0f}s -> {out}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("../data/processed/ibm_hi_small.parquet"))
    parser.add_argument("--out", type=Path, default=Path("../data/eval.json"))
    parser.add_argument("--model-out", type=Path, default=Path("../data/models/ibm_lgbm.txt"))
    parser.add_argument("--rows", type=int, default=None, help="only the first N rows (for a quick check)")
    parser.add_argument("--cache", type=Path, default=Path("../data/replay_cache"),
                        help="folder for the saved engine replay; reused if present, so reruns skip the replay")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache and replay again")
    args = parser.parse_args()
    if args.refresh:
        for f in ("replay.npz", "replay.json"):
            (args.cache / f).unlink(missing_ok=True)
    run(args.data, args.out, args.model_out, args.rows, args.cache)


if __name__ == "__main__":
    main()
