"""IBM AML loader: HI-Small_Trans.csv (+ HI-Small_Patterns.txt) -> one Parquet the engine replays.

    python -m ripple.data.ibm --raw ../data/raw --out ../data/processed/ibm_hi_small.parquet

Each row keeps the ripple.schema.Transaction columns plus labels for training and evaluation:
is_laundering (0/1), pattern (fan_in, cycle, ... or empty), attempt_id (the laundering attempt's number in the
patterns file, -1 if none), orig_amount and orig_currency. Transaction ignores
the extra columns, so replay.load_transactions reads the file as is.

Bank and account are joined into one account ID ("<bank>:<account>"), because IBM account numbers repeat across
banks. Amounts are converted to USD with rates taken from the dataset's own cross-currency rows, which is how IBM
generated them. Zero amounts are dropped (Transaction needs amount > 0). Device and location stay empty: IBM has
neither.
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

import pandas as pd

from ripple.schema import IBM_PAYMENT_FORMATS

COLUMNS = ["ts", "from_bank", "from_account", "to_bank", "to_account", "amount_received", "receiving_currency",
           "amount_paid", "payment_currency", "payment_format", "is_laundering"]
KEY = ["ts", "from_bank", "from_account", "to_bank", "to_account", "amount_paid", "payment_currency",
       "payment_format"]
_BEGIN = re.compile(r"BEGIN LAUNDERING ATTEMPT - ([A-Z-]+)")


def read_raw(path) -> pd.DataFrame:
    """Reads the IBM transaction CSV with bank and account IDs kept as text (leading zeros matter)."""
    df = pd.read_csv(path, header=0, names=COLUMNS,
                     dtype={"from_bank": str, "from_account": str, "to_bank": str, "to_account": str,
                            "receiving_currency": str, "payment_currency": str, "payment_format": str})
    df["ts"] = pd.to_datetime(df["ts"], format="%Y/%m/%d %H:%M")
    return df


def usd_rates(df: pd.DataFrame) -> dict[str, float]:
    """USD per unit of each currency: the median of received over paid on rows paid in that currency and received in
    US dollars, or failing that the reverse. The same rule as scripts/benchmark.py, so both give identical amounts."""
    df = df[(df["amount_paid"] > 0) & (df["amount_received"] > 0)]
    rates = {"US Dollar": 1.0}
    to_usd = df[(df["receiving_currency"] == "US Dollar") & (df["payment_currency"] != "US Dollar")]
    for cur, g in to_usd.groupby("payment_currency"):
        rates[cur] = float((g["amount_received"] / g["amount_paid"]).median())
    from_usd = df[(df["payment_currency"] == "US Dollar") & (df["receiving_currency"] != "US Dollar")]
    for cur, g in from_usd.groupby("receiving_currency"):
        rates.setdefault(cur, float((g["amount_paid"] / g["amount_received"]).median()))
    missing = set(df["payment_currency"]) - set(rates)
    if missing:
        raise ValueError(f"no conversion path to USD for {sorted(missing)}")
    return rates


def read_patterns(path: str | Path) -> pd.DataFrame:
    """Parses HI-Small_Patterns.txt into one row per laundering transaction with its pattern name and attempt number
    (one attempt per BEGIN/END block)."""
    lines, names, attempts, pattern, attempt = [], [], [], None, -1
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if begin := _BEGIN.match(line):
            pattern = begin.group(1).lower().replace("-", "_")
            attempt += 1
        elif line.startswith("END LAUNDERING"):
            pattern = None
        elif line and pattern:
            lines.append(line)
            names.append(pattern)
            attempts.append(attempt)
    # Parsed with the same reader as the transactions, so float amounts match exactly in the join.
    df = read_raw(io.StringIO("header\n" + "\n".join(lines)))
    df["pattern"] = names
    df["attempt_id"] = attempts
    return df[KEY + ["pattern", "attempt_id"]].drop_duplicates(KEY)


def transform(df: pd.DataFrame, patterns: pd.DataFrame | None = None,
              rates: dict[str, float] | None = None) -> pd.DataFrame:
    """Maps raw IBM rows to Transaction columns plus labels, sorted by time. txn_id is the CSV row number."""
    rates = rates or usd_rates(df)
    df = df.reset_index(drop=True)
    if patterns is not None:
        df = df.merge(patterns, on=KEY, how="left", validate="many_to_one")
    else:
        df["pattern"] = None
        df["attempt_id"] = -1
    out = pd.DataFrame({
        "txn_id": "ibm-" + df.index.astype(str),
        "ts": df["ts"],
        "src_account": df["from_bank"] + ":" + df["from_account"],
        "dst_account": df["to_bank"] + ":" + df["to_account"],
        "amount": (df["amount_paid"] * df["payment_currency"].map(rates)).round(2),
        "currency": "USD",
        "rail": df["payment_format"].map(lambda f: IBM_PAYMENT_FORMATS[f].value),
        "src_handle": None,
        "device_id": None,
        "location": None,
        "channel": None,
        "is_laundering": df["is_laundering"].astype("int8"),
        "pattern": df["pattern"].fillna(""),
        "attempt_id": df["attempt_id"].fillna(-1).astype("int32"),
        "orig_amount": df["amount_paid"],
        "orig_currency": df["payment_currency"],
    })
    out = out[out["amount"] > 0]
    return out.sort_values("ts", kind="stable").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", default="../data/raw", help="folder with HI-Small_Trans.csv and HI-Small_Patterns.txt")
    parser.add_argument("--prefix", default="HI-Small", help="dataset size and illicit ratio, e.g. HI-Small, LI-Medium")
    parser.add_argument("--out", default="../data/processed/ibm_hi_small.parquet")
    args = parser.parse_args()

    raw = Path(args.raw)
    df = read_raw(raw / f"{args.prefix}_Trans.csv")
    patterns_path = raw / f"{args.prefix}_Patterns.txt"
    patterns = read_patterns(patterns_path) if patterns_path.exists() else None
    rates = usd_rates(df)
    out = transform(df, patterns, rates)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    tagged = (out["pattern"] != "").sum()
    print(f"{len(out):,} rows -> {args.out} ({len(df) - len(out):,} zero amounts dropped)")
    print(f"laundering {out['is_laundering'].sum():,}, tagged with a pattern {tagged:,}")
    print(f"{out['ts'].min()} to {out['ts'].max()}")
    for cur, rate in sorted(rates.items(), key=lambda kv: kv[0]):
        print(f"  1 {cur} = {rate:.6g} USD")


if __name__ == "__main__":
    main()
