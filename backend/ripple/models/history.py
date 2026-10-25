"""Per-account payment history for the model layer: how an account has paid and been paid so far.

LightGBMModel keeps one AccountHistory and updates it on every payment it scores, so these features need no change to
the engine's feature store. Transfers to the same account are never scored, but they still belong in the history
(on IBM, ordinary accounts reinvest into themselves and laundering accounts rarely do), so the engine should pass
them to LightGBMModel.observe. ripple.eval.ibm builds its training matrix with the same class over every payment in
stream order, so training and serving cannot drift apart. Each payment's features describe only the payments before
it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ripple.schema import Rail, Transaction

HISTORY_FEATURES = [
    "src_ach_share",  # share of the payer's earlier outgoing payments that were ACH
    "dst_ach_share",  # share of the payee's earlier incoming payments that were ACH
    "src_hours_since_last",  # since the payer's previous outgoing payment
    "dst_hours_since_last",  # since the payee's previous incoming payment
    "src_payments_before",
    "dst_receipts_before",
    "amount_vs_src_mean",  # log amount against the payer's mean log amount so far
    "dst_mean_log_amount",  # the payee's mean log amount received so far
]
NONE = -1.0  # no earlier payment to describe


@dataclass(slots=True)
class _Side:
    n: int = 0
    ach: int = 0
    log_amount: float = 0.0
    last_ts: float | None = None


class AccountHistory:
    def __init__(self) -> None:
        self.out: dict[str, _Side] = {}
        self.inc: dict[str, _Side] = {}

    def features(self, txn: Transaction) -> dict[str, float]:
        src, dst = self.out.get(txn.src_account), self.inc.get(txn.dst_account)
        ts = txn.ts.timestamp()
        log_amount = math.log1p(max(txn.amount, 0.0))
        return {
            "src_ach_share": src.ach / src.n if src else NONE,
            "dst_ach_share": dst.ach / dst.n if dst else NONE,
            "src_hours_since_last": (ts - src.last_ts) / 3600 if src else NONE,
            "dst_hours_since_last": (ts - dst.last_ts) / 3600 if dst else NONE,
            "src_payments_before": float(src.n) if src else 0.0,
            "dst_receipts_before": float(dst.n) if dst else 0.0,
            "amount_vs_src_mean": log_amount - src.log_amount / src.n if src else 0.0,
            "dst_mean_log_amount": dst.log_amount / dst.n if dst else NONE,
        }

    def update(self, txn: Transaction) -> None:
        ts = txn.ts.timestamp()
        log_amount = math.log1p(max(txn.amount, 0.0))
        is_ach = txn.rail == Rail.ACH or txn.rail == Rail.ACH.value
        for side in (self.out.setdefault(txn.src_account, _Side()), self.inc.setdefault(txn.dst_account, _Side())):
            side.n += 1
            side.ach += is_ach
            side.log_amount += log_amount
            side.last_ts = ts

    def observe(self, txn: Transaction) -> dict[str, float]:
        """This payment's features from the history before it, then the payment is added to the history."""
        features = self.features(txn)
        self.update(txn)
        return features
