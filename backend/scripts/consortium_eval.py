"""Consortium uplift on IBM AML: how much more laundering do member banks catch when they share keyed hashes of
flagged accounts, against each bank working alone?

    python scripts/consortium_eval.py ../data/raw/HI-Small_Trans.csv --rows 1500000 --banks 8

Member banks are the ones with the most payments in the slice. A laundering payment that touches a member bank
counts as caught if any member bank alerts on it. The first 48 hours are left out (engine warm-up), and so are
transfers from an account to itself. Writes data/consortium.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark import load, transactions  # noqa: E402

from ripple.consortium import Consortium, bank_of  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "consortium.json"


def run(df, banks: list[str], sharing: bool) -> dict:
    con = Consortium(banks, sharing=sharing)
    members = set(banks)
    caught = missed = false_alerts = alerts = 0
    started = time.perf_counter()
    for txn, label in transactions(df):
        if txn.src_account == txn.dst_account or not ({bank_of(txn.src_account), bank_of(txn.dst_account)} & members):
            continue
        results = con.process(txn)
        if any(e.warming_up(txn.ts) for e in con.engines.values()):
            continue
        alerted = any(s.is_alert for s in results.values())
        alerts += alerted
        if label:
            caught += alerted
            missed += not alerted
        else:
            false_alerts += alerted
    laundering = caught + missed
    return {
        "mode": "consortium" if sharing else "each bank alone",
        "laundering_payments": laundering,
        "caught": caught,
        "recall": round(caught / laundering, 4) if laundering else None,
        "alerts": alerts,
        "precision": round(caught / alerts, 4) if alerts else None,
        "false_alerts": false_alerts,
        "seconds": round(time.perf_counter() - started, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--rows", type=int, default=1_500_000)
    parser.add_argument("--banks", type=int, default=8)
    args = parser.parse_args()

    df, info = load(args.csv, args.rows)
    df = df[(df.src_bank + "-" + df.src_acct) != (df.dst_bank + "-" + df.dst_acct)]
    counts = df.src_bank.value_counts().add(df.dst_bank.value_counts(), fill_value=0)
    banks = [str(b) for b in counts.sort_values(ascending=False).index[: args.banks]]
    print(json.dumps({"banks": banks, **info}), flush=True)
    alone = run(df, banks, sharing=False)
    print(json.dumps(alone), flush=True)
    shared = run(df, banks, sharing=True)
    print(json.dumps(shared), flush=True)
    report = {"dataset": "IBM AML HI-Small", "rows": int(len(df)), "member_banks": banks, "results": [alone, shared],
              "note": "Banks share only HMAC-SHA256 tokens of flagged account IDs with a timestamp; no amounts, names "
                      "or account numbers leave a bank."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
