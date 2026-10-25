"""One-shot pattern learning on IBM AML: learn from one laundering attempt of each type, then catch the rest.

    python scripts/oneshot_ibm.py                    # all of HI-Small, writes data/oneshot_ibm.json
    python scripts/oneshot_ibm.py --rows 1000000     # a quick check on the first million rows

One pass over the transactions in time order, with only the relay tracker from ripple.motifs (the full engine is not
needed to learn or match a motif). For each IBM pattern type, the first attempt that starts after the tracker's
warm-up is the single example. When its last payment has been seen, a motif is learned from that attempt's payments
against everything the tracker has seen so far, with the same learner the live demo uses, and deployed from that
moment on. Labels are used only to pick the example and to score the result.

An attempt counts as caught when a motif matches one of its payments; "in time" means the match came before the
attempt's last payment, while there was still money to hold. Legitimate matches are payments IBM does not label as
laundering. A type whose example has no account that received money and passed it on (fan-out, for instance) cannot
be learned from its relay shape, and that is reported as such.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ripple import motifs  # noqa: E402
from ripple.motifs import RelayTracker, learn  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Row:
    """The fields RelayTracker reads from a Transaction, without pydantic's cost on five million rows."""

    txn_id: str
    ts: datetime
    src_account: str
    dst_account: str
    amount: float
    rail: str


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "processed" / "ibm_hi_small.parquet")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "oneshot_ibm.json")
    parser.add_argument("--rows", type=int, default=None)
    parser.add_argument("--max-per-day", type=float, default=20.0,
                        help="false alarms a day a learned motif may add, judged on the history seen so far")
    parser.add_argument("--history-days", type=int, default=7, help="background the learner checks against")
    args = parser.parse_args()
    motifs.HISTORY = timedelta(days=args.history_days)

    t0 = time.perf_counter()
    df = pd.read_parquet(args.data, columns=["txn_id", "ts", "src_account", "dst_account", "amount", "rail",
                                             "is_laundering", "pattern", "attempt_id"])
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    if args.rows:
        df = df.iloc[: args.rows]
    start = df["ts"].iloc[0]
    settled = start + motifs.WARMUP + timedelta(hours=1)

    tagged = df[df["attempt_id"] >= 0]
    attempts = tagged.groupby("attempt_id").agg(pattern=("pattern", "first"), first=("ts", "min"), last=("ts", "max"))
    txns_of = tagged.groupby("attempt_id")["txn_id"].apply(set).to_dict()
    attempt_of = dict(zip(tagged["txn_id"], tagged["attempt_id"]))
    examples = {}
    for pattern, group in attempts[attempts["first"] >= settled].sort_values("first").groupby("pattern"):
        examples[pattern] = int(group.index[0])
    last_txn = {}  # the example's last payment in stream order -> pattern
    for pattern, a in examples.items():
        ids = txns_of[a]
        last_txn[df.loc[df["txn_id"].isin(ids), "txn_id"].iloc[-1]] = pattern
    print(f"{len(df):,} rows loaded in {time.perf_counter() - t0:.0f}s; examples: {examples}", flush=True)

    tracker = RelayTracker()
    live: dict[str, motifs.Motif] = {}
    deployed_at: dict[str, datetime] = {}
    learned: dict[str, dict] = {}
    caught: dict[str, dict[int, datetime]] = defaultdict(dict)  # pattern's motif -> attempt -> first match time
    legit = defaultdict(int)
    matched = defaultdict(int)
    labels = dict(zip(df["txn_id"], df["is_laundering"]))

    cols = zip(df["txn_id"], df["ts"], df["src_account"], df["dst_account"], df["amount"], df["rail"])
    for n, (txn_id, ts, src, dst, amount, rail) in enumerate(cols):
        row = Row(txn_id, ts.to_pydatetime(), src, dst, float(amount), rail)
        event = tracker.observe(row)
        if event is not None:
            for pattern, motif in live.items():
                if motif.matches(event):
                    matched[pattern] += 1
                    if labels[txn_id]:
                        a = attempt_of.get(txn_id)
                        if a is not None:
                            caught[pattern].setdefault(a, row.ts)
                    else:
                        legit[pattern] += 1
        if txn_id in last_txn:
            pattern = last_txn[txn_id]
            a = examples[pattern]
            try:
                motif = learn(tracker, txns_of[a], f"IBM-{pattern}", f"one {pattern} attempt",
                              max_per_day=args.max_per_day)
                motif.deployed = True
                live[pattern] = motif
                deployed_at[pattern] = row.ts
                learned[pattern] = {"rules": [c.describe() for c in motif.constraints],
                                    "expected_false_alarms_per_day": round(motif.false_alarms_per_day, 2)}
                print(f"  learned {pattern} at {row.ts}: {learned[pattern]}", flush=True)
            except ValueError as err:
                learned[pattern] = {"error": str(err)}
                print(f"  could not learn {pattern}: {err}", flush=True)
        if n and n % 500_000 == 0:
            print(f"  {n:,} rows in {time.perf_counter() - t0:.0f}s", flush=True)

    end = df["ts"].iloc[-1]
    per_type = []
    for pattern in sorted(examples):
        info = {"type": pattern, "example_attempt": examples[pattern], **learned.get(pattern, {"error": "not reached"})}
        if pattern in live:
            since = deployed_at[pattern]
            later = attempts[(attempts["first"] > since)]
            same = later[later["pattern"] == pattern]
            hits = caught[pattern]
            days = max((end - since).total_seconds() / 86400, 1e-9)
            info.update({
                "deployed_at": since.isoformat(),
                "attempts_after": int(len(same)),
                "caught_same_type": int(sum(a in hits for a in same.index)),
                "caught_same_type_in_time": int(sum(a in hits and hits[a] < same.loc[a, "last"] for a in same.index)),
                "attempts_after_any_type": int(len(later)),
                "caught_any_type": int(sum(a in hits for a in later.index)),
                "matches": matched[pattern],
                "legit_matches": legit[pattern],
                "legit_matches_per_day": round(legit[pattern] / days, 2),
                "days_live": round(days, 1),
            })
        per_type.append(info)
        print(" ", info, flush=True)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": "IBM AML HI-Small",
        "rows": len(df),
        "days": round((end - start).total_seconds() / 86400, 1),
        "max_false_alarms_per_day": args.max_per_day,
        "history_days": args.history_days,
        "per_type": per_type,
        "seconds": round(time.perf_counter() - t0),
        "notes": [
            "Each motif is learned from one laundering attempt only, with no other labels, and deployed from the moment "
            "that attempt's last payment is seen. Later attempts are ones that start after that moment.",
            f"The learner may add at most {args.max_per_day:g} false alarms a day, judged on the last "
            f"{args.history_days} days of traffic seen so far. IBM HI-Small carries about 280,000 payments a day.",
            "Caught in time means a motif matched one of the attempt's payments before its last payment.",
            "Types with no account that received money and passed it on cannot be learned from a relay shape.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"done in {report['seconds']}s -> {args.out}")


if __name__ == "__main__":
    main()
