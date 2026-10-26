"""Measures golden-hour tracing on IBM AML HI-Small and writes data/trace_eval.json.

    python scripts/trace_ibm.py --data ../data/processed/ibm_hi_small.parquet

IBM has no victim reports, so each tagged laundering attempt on the test days stands in for one: the report names
the account that made the attempt's first payment, its time and its amount. The live engine (ibm_aml pack) replays
the stream in time order, and at fixed delays after that first payment (10 minutes, 1 hour, 6 hours, 24 hours) the
trace runs on the engine as it stands then, exactly as POST /trace would. For each trace the script records:

- located: the share of the attempt's money paid so far that the traced trail contains (and the share of payments)
- trail precision: the share of the trail's payments that are laundering of any attempt
- the hold plan: how many liens it proposes, the traced amount held under the three tracing rules, and how much of
  it sits on accounts that took part in the attempt
- top-k: what the k largest proposed liens would hold, as a share of the money traced into the trail

Test days follow ripple/eval/ibm.py: the last 30% of full days. The sparse tail is replayed but not scored.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ripple.engine import Engine  # noqa: E402
from ripple.schema import Rail, Transaction  # noqa: E402
from ripple.trace import trace  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "trace_eval.json"
DELAYS = {"10m": timedelta(minutes=10), "1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24)}
TOP_K = (1, 3, 5)
# How the report starts the trace: naming the paid amount (the 3 closest payments), or every payment to a new payee.
MODES = {"named_amount": True, "new_payees": False}
TRAIN_SHARE = 0.7
TAIL_SHARE = 0.01


def test_attempts(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    day = df["ts"].dt.floor("D")
    per_day = day.value_counts()
    full = sorted(per_day[per_day >= TAIL_SHARE * per_day.max()].index)
    test_days = full[math.ceil(TRAIN_SHARE * len(full)):]
    start, end = test_days[0], test_days[-1] + pd.Timedelta(days=1)
    tagged = df[(df["attempt_id"] >= 0) & (df["pattern"] != "")]
    first = tagged.sort_values("ts").groupby("attempt_id").first()  # includes txn_id
    first = first[(first["ts"] >= start) & (first["ts"] < end)]
    return first, start, end


def summarise(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    a = np.asarray(values, dtype=float)
    return {"n": int(len(a)), "mean": round(float(a.mean()), 4), "median": round(float(np.median(a)), 4)}


def run(data: Path, out: Path, rows: int | None) -> dict:
    t0 = time.perf_counter()
    df = pd.read_parquet(data, columns=["txn_id", "ts", "src_account", "dst_account", "amount", "rail",
                                        "is_laundering", "pattern", "attempt_id"])
    if rows:
        df = df.iloc[:rows]
    first, test_start, test_end = test_attempts(df)
    laundering_ids = set(df.loc[df["is_laundering"] == 1, "txn_id"])
    by_attempt = {a: g for a, g in df[df["attempt_id"].isin(first.index)].groupby("attempt_id")}
    checks = [(row.ts.to_pydatetime() + delay, label, int(a)) for a, row in first.iterrows()
              for label, delay in DELAYS.items()]
    heapq.heapify(checks)
    print(f"{len(df):,} rows; {len(first)} test attempts; {len(checks)} traces; loaded in "
          f"{time.perf_counter() - t0:.0f}s", flush=True)

    engine = Engine("ibm_aml")
    rails = {r.value: r for r in Rail}
    results: list[dict] = []

    def reachable(paid: pd.DataFrame, f) -> pd.DataFrame:
        """The attempt's later payments a forward trace could reach at all: the first payer's own later payments,
        and payments by any account after money on this attempt reached it."""
        arrived = {f["src_account"]: f["ts"], f["dst_account"]: f["ts"]}
        keep = []
        for row in paid.sort_values("ts").itertuples():
            if row.txn_id == f["txn_id"]:
                continue
            if row.src_account in arrived and row.ts >= arrived[row.src_account]:
                keep.append(row.Index)
                arrived.setdefault(row.dst_account, row.ts)
        return paid.loc[keep]

    def run_trace(label: str, attempt: int) -> None:
        f = first.loc[attempt]
        now = engine.store.now
        paid = by_attempt[attempt]
        paid = paid[paid["ts"] <= pd.Timestamp(now)]
        later = paid[paid["txn_id"] != f["txn_id"]]
        reach = reachable(paid, f)
        for mode, amount in MODES.items():
            plan = trace(engine, f["src_account"], f["ts"].to_pydatetime(), amount=float(f["amount"]) if amount else None)
            entry = {"attempt": attempt, "pattern": f["pattern"], "delay": label, "mode": mode,
                     "payments_so_far": int(len(paid)), "later_payments": int(len(later)),
                     "reachable_payments": int(len(reach))}
            if plan is None:
                results.append(entry | {"found": False})
                continue
            trail = {e.txn_id for e in plan.edges} if plan.edges else set()
            attempt_accounts = set(paid["src_account"]) | set(paid["dst_account"])
            holds = sorted(plan.freeze, key=lambda h: -(h.hold_low if h.hold_low is not None else h.recoverable))
            low = [h.hold_low if h.hold_low is not None else h.recoverable for h in holds]
            share = lambda rows: (round(float(rows.loc[rows["txn_id"].isin(trail), "amount"].sum())
                                        / float(rows["amount"].sum()), 4) if len(rows) else None)
            entry |= {
                "found": True,
                "first_payment_on_trail": f["txn_id"] in trail,
                "located_later_share": share(later),
                "located_reachable_share": share(reach),
                "trail_payments": len(trail),
                "trail_precision": round(len(trail & laundering_ids) / max(len(trail), 1), 4),
                "traced_in": round(plan.stolen, 2),
                "escaped": round(plan.escaped, 2),
                "holds": len(holds),
                "held_low": round(sum(low), 2),
                "held_high": round(plan.recoverable_high or plan.recoverable_now, 2),
                "held_on_attempt_accounts": round(sum(v for h, v in zip(holds, low) if h.account_id in attempt_accounts),
                                                  2),
                "top_k_held_share": {str(k): round(sum(low[:k]) / max(plan.stolen, 1e-9), 4) for k in TOP_K},
            }
            results.append(entry)

    cols = zip(df["txn_id"], df["ts"], df["src_account"], df["dst_account"], df["amount"], df["rail"])
    started = time.perf_counter()
    for i, (txn_id, ts, src, dst, amount, rail) in enumerate(cols):
        ts = ts.to_pydatetime()
        while checks and checks[0][0] <= ts:
            _, label, attempt = heapq.heappop(checks)
            run_trace(label, attempt)
        if ts >= test_end + max(DELAYS.values()) and not checks:
            break
        txn = Transaction.model_construct(txn_id=txn_id, ts=ts, src_account=src, dst_account=dst, amount=float(amount),
                                          currency="USD", rail=rails[rail], src_handle=None, device_id=None,
                                          location=None, channel=None)
        engine.process(txn)
        if i and i % 250_000 == 0:
            print(f"{i:,} rows, {(i + 1) / (time.perf_counter() - started):,.0f} rows/s, {len(results)} traces done",
                  flush=True)
    while checks:  # checks due after the last row run on the final state
        _, label, attempt = heapq.heappop(checks)
        run_trace(label, attempt)

    def stats(rs: list[dict], key: str) -> dict:
        return summarise([r[key] for r in rs if r.get(key) is not None])

    by_delay = []
    for mode in MODES:
        for label in DELAYS:
            rs = [r for r in results if r["delay"] == label and r["mode"] == mode]
            found = [r for r in rs if r["found"]]
            by_delay.append({
                "mode": mode,
                "delay": label,
                "attempts": len(rs),
                "trace_found": len(found),
                "attempts_with_later_payments": sum(r["later_payments"] > 0 for r in rs),
                "first_payment_on_trail": round(sum(r["first_payment_on_trail"] for r in found) / max(len(found), 1), 4),
                "located_later_share": stats(found, "located_later_share"),
                "located_reachable_share": stats(found, "located_reachable_share"),
                "trail_precision": stats(found, "trail_precision"),
                "holds": stats(found, "holds"),
                "held_low_share": summarise([r["held_low"] / r["traced_in"] for r in found if r["traced_in"] > 0]),
                "held_high_share": summarise([r["held_high"] / r["traced_in"] for r in found if r["traced_in"] > 0]),
                "held_on_attempt_accounts_share": summarise(
                    [r["held_on_attempt_accounts"] / r["held_low"] for r in found if r["held_low"] > 0]),
                "top_k_held_share": {str(k): summarise([r["top_k_held_share"][str(k)] for r in found]) for k in TOP_K},
            })
    by_pattern = []
    for pattern in sorted({r["pattern"] for r in results}):
        rs = [r for r in results if r["pattern"] == pattern and r["delay"] == "6h" and r["found"]]
        by_pattern.append({"pattern": pattern, **{
            mode: {"traces": sum(r["mode"] == mode for r in rs),
                   "located_reachable_share": stats([r for r in rs if r["mode"] == mode], "located_reachable_share")}
            for mode in MODES}})
    report = {
        "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        "dataset": f"IBM AML {data.stem}",
        "test_days": f"{test_start.date()} to {(test_end - pd.Timedelta(days=1)).date()}",
        "attempts": int(len(first)),
        "by_delay": by_delay,
        "by_pattern_at_6h": by_pattern,
        "per_trace": results,
        "notes": [
            "IBM has no victim reports. Each test-day laundering attempt stands in for one: the trace starts from the "
            "account that made the attempt's first payment, at that payment's time, naming its amount.",
            "Each trace runs on the live engine's state at the stated delay after that first payment, as POST /trace "
            "would. It can only follow payments inside the engine's 72-hour window and one bank's view.",
            "The reported first payment is always where the trace starts, so it is not scored. located_later_share is "
            "the share of the attempt's later money (paid by the stated delay) that the trail contains; "
            "located_reachable_share counts only later payments a forward trace could reach at all (the first payer's "
            "own later payments, and payments by accounts the attempt's money had reached). Fan-in and bipartite "
            "attempts have many payers, most of them unreachable from one report.",
            "Two report styles are compared: naming the paid amount (the trace starts from the 3 closest payments) "
            "and naming none (it starts from every payment to a new payee from that time).",
            "trail_precision is the share of the trail's payments that are laundering of any attempt.",
            "held_low and held_high are the liens the plan proposes under the three tracing rules (haircut, FIFO, "
            "LIBR), as shares of the money traced into the trail. top_k_held_share uses each lien's lowest figure.",
            "IBM amounts are in US dollars.",
        ] + ([f"Only the first {rows:,} rows."] if rows else []),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(by_delay, indent=1), flush=True)
    print(f"done in {time.perf_counter() - t0:,.0f}s -> {out}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("../data/processed/ibm_hi_small.parquet"))
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--rows", type=int, default=None, help="only the first N rows (for a quick check)")
    args = parser.parse_args()
    run(args.data, args.out, args.rows)


if __name__ == "__main__":
    main()
