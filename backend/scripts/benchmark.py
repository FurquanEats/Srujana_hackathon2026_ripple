"""Scale benchmark: replays IBM AML transactions through the engine and reports speed, memory and a first quality check.

    python scripts/benchmark.py ../data/raw/HI-Small_Trans.csv --rows 500000 [--profile]

Amounts are converted to USD with rates implied by the dataset's own cross-currency rows, so no outside rate table
is needed. Quality numbers here are transaction-level alert precision and recall against the dataset's labels, a
sanity check only; the full evaluation lives in ripple.eval. Rows in the warm-up period and transfers from an account
to itself are left out of the quality numbers, because the engine never alerts on them.
"""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ripple.engine import Engine  # noqa: E402
from ripple.schema import IBM_PAYMENT_FORMATS, Transaction  # noqa: E402

COLUMNS = ["ts", "src_bank", "src_acct", "dst_bank", "dst_acct", "amt_recv", "cur_recv", "amt_paid", "cur_paid", "fmt", "label"]


def usd_rates(df: pd.DataFrame) -> dict[str, float]:
    """USD per unit of each currency, from rows that pay in one currency and receive US dollars (or the reverse)."""
    rates = {"US Dollar": 1.0}
    to_usd = df[(df.cur_recv == "US Dollar") & (df.cur_paid != "US Dollar")]
    for cur, g in to_usd.groupby("cur_paid"):
        rates[cur] = float((g.amt_recv / g.amt_paid).median())
    from_usd = df[(df.cur_paid == "US Dollar") & (df.cur_recv != "US Dollar")]
    for cur, g in from_usd.groupby("cur_recv"):
        rates.setdefault(cur, float((g.amt_paid / g.amt_recv).median()))
    return rates


def load(path: Path, rows: int | None) -> tuple[pd.DataFrame, dict]:
    """Reads, sorts and converts the CSV into one table. Transactions are built from it one at a time while scoring,
    because holding millions of Transaction objects at once would not fit in a laptop's memory."""
    df = pd.read_csv(path, nrows=rows, header=0, names=COLUMNS, dtype={"src_bank": str, "dst_bank": str})
    df["ts"] = pd.to_datetime(df.ts, format="%Y/%m/%d %H:%M")
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    rates = usd_rates(df)
    df["usd"] = df.amt_paid * df.cur_paid.map(rates)
    dropped = int(df.usd.isna().sum() + (df.usd <= 0).sum())
    df = df[df.usd > 0][["ts", "src_bank", "src_acct", "dst_bank", "dst_acct", "usd", "fmt", "label"]]
    info = {"rows_read": int(len(df) + dropped), "rows_dropped": dropped, "first_ts": str(df.ts.min()),
            "last_ts": str(df.ts.max()), "currencies": len(rates), "laundering_rows": int(df.label.sum())}
    return df, info


def transactions(df: pd.DataFrame) -> Iterator[tuple[Transaction, int]]:
    for i, ts, sb, sa, db, da, usd, fmt, label in zip(
        df.index, df.ts, df.src_bank, df.src_acct, df.dst_bank, df.dst_acct, df.usd, df.fmt, df.label
    ):
        yield Transaction.model_construct(
            txn_id=f"I{i}", ts=ts.to_pydatetime(), src_account=f"{sb}-{sa}", dst_account=f"{db}-{da}",
            amount=float(usd), currency="USD", rail=IBM_PAYMENT_FORMATS[fmt],
            src_handle=None, device_id=None, location=None, channel=None,
        ), int(label)


def run(df: pd.DataFrame, pack: str) -> dict:
    engine = Engine(pack)
    proc = psutil.Process()
    rss_start = proc.memory_info().rss
    checkpoints = []
    tp = fp = fn = 0
    started = time.perf_counter()
    for n, (txn, label) in enumerate(transactions(df), 1):
        scored, _ = engine.process(txn)
        if engine.warming_up(txn.ts) or txn.src_account == txn.dst_account:
            pass  # not scored for alerts: warm-up period, or a transfer to the same account
        elif scored.is_alert:
            tp += label
            fp += 1 - label
        else:
            fn += label
        if n % 100_000 == 0:
            elapsed = time.perf_counter() - started
            checkpoints.append({"rows": n, "seconds": round(elapsed, 1), "tps": round(n / elapsed),
                                "rss_mb": round(proc.memory_info().rss / 2**20)})
            print(json.dumps(checkpoints[-1]), flush=True)
    elapsed = time.perf_counter() - started
    stats = engine.stats()
    return {
        "rows": len(df),
        "seconds": round(elapsed, 1),
        "tps": round(len(df) / elapsed),
        "p95_latency_ms": stats["p95_latency_ms"],
        "rss_mb_start": round(rss_start / 2**20),
        "rss_mb_end": round(proc.memory_info().rss / 2**20),
        "accounts": len(engine.store.accounts),
        "alerts": int(stats["alerts"]),
        "cases": len(engine.cases.cases),
        "alert_precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "alert_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "checkpoints": checkpoints,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--pack", default="ibm_aml")
    parser.add_argument("--profile", action="store_true", help="print the 25 most expensive functions")
    args = parser.parse_args()

    t0 = time.perf_counter()
    df, info = load(args.csv, args.rows)
    info["load_seconds"] = round(time.perf_counter() - t0, 1)
    print(json.dumps(info), flush=True)

    if args.profile:
        profiler = cProfile.Profile()
        result = profiler.runcall(run, df, args.pack)
        pstats.Stats(profiler).sort_stats("cumulative").print_stats(25)
    else:
        result = run(df, args.pack)
    print(json.dumps(result | {"load": info}, indent=2))


if __name__ == "__main__":
    main()
