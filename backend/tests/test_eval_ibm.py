"""IBM evaluation: money recoverable at first alert, and an end-to-end run on a tiny synthetic dataset."""

import json
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from ripple.eval.ibm import recoverable_at_first_alert
from ripple.schema import EvalReport


def test_rail_features_match_between_training_and_serving():
    from ripple.models.lgbm import RAIL_FEATURES, rail_features, rail_matrix
    from ripple.schema import Rail

    served = rail_features(Rail.ACH)
    assert list(served) == RAIL_FEATURES and sum(served.values()) == 1.0 and served["rail_ach"] == 1.0
    trained = rail_matrix(np.array(["ACH", "CASH"]))
    assert trained.shape == (2, len(RAIL_FEATURES))
    assert dict(zip(RAIL_FEATURES, trained[0])) == served


def test_history_features_match_between_training_and_serving():
    from ripple.eval.ibm import history_matrix
    from ripple.models.history import HISTORY_FEATURES, AccountHistory
    from ripple.schema import Rail, Transaction

    t0 = datetime(2022, 9, 1)
    rows = pd.DataFrame({
        "txn_id": ["a", "b", "c", "d"],
        "ts": pd.to_datetime([t0, t0 + timedelta(hours=1), t0 + timedelta(hours=2), t0 + timedelta(hours=5)]),
        "src_account": ["X", "X", "Y", "X"],
        "dst_account": ["Y", "X", "Z", "Z"],  # b is a transfer to the same account: history only, never scored
        "amount": [100.0, 50.0, 90.0, 400.0],
        "rail": ["ACH", "REINVESTMENT", "ACH", "WIRE"],
    })
    trained = history_matrix(rows)
    served = AccountHistory()
    for row in rows.itertuples():
        txn = Transaction.model_construct(txn_id=row.txn_id, ts=row.ts.to_pydatetime(), src_account=row.src_account,
                                          dst_account=row.dst_account, amount=row.amount, rail=Rail(row.rail))
        if row.src_account == row.dst_account:
            served.update(txn)  # what LightGBMModel.observe does
            continue
        f = served.observe(txn)
        assert list(trained[row.Index]) == pytest.approx([f[k] for k in HISTORY_FEATURES])
    f = dict(zip(HISTORY_FEATURES, trained[3]))
    assert f["src_payments_before"] == 2 and f["src_ach_share"] == 0.5  # a (ACH) and the reinvestment b
    assert f["src_hours_since_last"] == 4.0 and f["dst_receipts_before"] == 1


def test_recoverable_counts_money_from_the_first_alert_on():
    t0 = datetime(2022, 9, 8)
    attempts = pd.DataFrame({
        "attempt_id": [0, 0, 0, 1, 1, -1],
        "ts": [t0, t0 + timedelta(hours=1), t0 + timedelta(hours=2), t0, t0 + timedelta(hours=1), t0],
        "amount": [100.0, 300.0, 600.0, 50.0, 50.0, 999.0],
    })
    alert = np.array([False, True, False, False, False, True])
    row = recoverable_at_first_alert("x", attempts, alert)
    assert row["attempts"] == 2 and row["alerted_share"] == 0.5
    assert row["mean_recoverable"] == 0.45  # attempt 0 still has 900 of 1000; attempt 1 was never alerted
    assert row["median_recoverable"] == 0.45


def _synthetic(days: int = 10, per_day: int = 400, seed: int = 3) -> pd.DataFrame:
    """Ordinary payments among 300 accounts, plus a fan-in-then-out ring each day tagged as one attempt."""
    rng = random.Random(seed)
    rows, attempt = [], 0
    for d in range(days):
        day = datetime(2022, 9, 1) + timedelta(days=d)
        for _ in range(per_day):
            a, b = rng.sample(range(300), 2)
            rows.append((day + timedelta(minutes=rng.randint(0, 1439)), f"001:{a}", f"001:{b}",
                         rng.uniform(50, 3000), "ACH", 0, "", -1))
        hub = f"002:H{d}"
        for i in range(6):
            rows.append((day + timedelta(hours=10, minutes=10 * i), f"003:S{d}_{i}", hub, 4000 + 100 * i, "WIRE", 1,
                         "fan_in", attempt))
        rows.append((day + timedelta(hours=11, minutes=20), hub, f"004:O{d}", 24000, "WIRE", 1, "fan_in", attempt))
        attempt += 1
    df = pd.DataFrame(rows, columns=["ts", "src_account", "dst_account", "amount", "rail", "is_laundering", "pattern",
                                     "attempt_id"]).sort_values("ts", kind="stable").reset_index(drop=True)
    df["txn_id"] = "ibm-" + df.index.astype(str)
    return df


def test_eval_runs_end_to_end_and_writes_a_valid_report(tmp_path):
    pytest.importorskip("lightgbm")
    pytest.importorskip("sklearn")
    pytest.importorskip("pyarrow")
    from ripple.eval.ibm import run

    data = tmp_path / "ibm.parquet"
    _synthetic().to_parquet(data, index=False)
    report = run(data, tmp_path / "eval.json", tmp_path / "model.txt", None)

    EvalReport.model_validate(json.loads((tmp_path / "eval.json").read_text()))
    assert (tmp_path / "model.txt").exists() and (tmp_path / "model.json").exists()
    assert [r["name"] for r in report["money_recoverable"]] == ["Ripple (full)", "Single-transaction baseline"]
    assert report["per_typology"][0]["name"].startswith("fan-in (fan_in_out)")
    assert "train on the first 7 of 10 days" in report["split"]
