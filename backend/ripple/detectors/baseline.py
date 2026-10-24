"""Behavioural baseline: is this unusual for these accounts, judged only against their own history?

Uses robust statistics (median and MAD), so one past outlier does not distort the baseline. On its own this layer
can only produce a Watch-level score (see ripple.fusion), because unusual is not the same as suspicious.
"""

from __future__ import annotations

from datetime import timedelta

from ripple.features.store import AccountState, baseline, hour_share, window
from ripple.fmt import money
from ripple.schema import Layer, Rail, Reason, Transaction

MIN_HISTORY = 5


def _reason(code: str, text: str, strength: float, txn_ids: list[str]) -> Reason:
    return Reason(layer=Layer.BASELINE, code=code, text=text, strength=round(min(1.0, strength), 3), txn_ids=txn_ids)


def score(txn: Transaction, src: AccountState, dst: AccountState) -> tuple[float, list[Reason], bool]:
    """Returns (score 0..1, reasons, whether the source had enough history to judge)."""
    reasons: list[Reason] = []
    has_history = True
    if txn.rail != Rail.CASH:
        b = baseline(src)
        has_history = b is not None and b.n >= MIN_HISTORY
        if has_history:
            z = b.z(txn.amount)
            if z >= 4 and txn.amount >= 3 * b.median:
                reasons.append(_reason(
                    "baseline_amount",
                    f"{money(txn.amount, txn.currency)} is {txn.amount / b.median:.0f} times {txn.src_account}'s usual payment "
                    f"(median {money(b.median, txn.currency)} over its last {b.n} payments)",
                    0.5 + 0.5 * min(1.0, (z - 4) / 12),
                    [txn.txn_id],
                ))
            share = hour_share(src, txn.ts.hour)
            if share is not None and share < 0.05:
                reasons.append(_reason(
                    "baseline_hour",
                    f"{txn.src_account} rarely pays around {txn.ts:%H}:00 ({share:.0%} of its past payments)",
                    0.35,
                    [txn.txn_id],
                ))
        burst = window(src.outgoing, txn.ts, timedelta(hours=1))
        if len(burst) >= 6:
            reasons.append(_reason(
                "baseline_velocity_out",
                f"{txn.src_account} made {len(burst)} payments in the last hour",
                0.4 + 0.05 * min(len(burst) - 6, 8),
                [e.txn_id for e in burst],
            ))

    inbound = window(dst.incoming, txn.ts, timedelta(hours=2))
    age_days = max(1.0, (txn.ts - dst.first_seen).total_seconds() / 86400)
    usual_per_day = max(1.0, (dst.received_total - len(inbound)) / age_days)
    if len(inbound) >= 5 and len(inbound) >= 5 * usual_per_day:
        reasons.append(_reason(
            "baseline_velocity_in",
            f"{txn.dst_account} usually receives about {usual_per_day:.0f} payment a day; it received {len(inbound)} in 2 hours",
            0.5 + 0.05 * min(len(inbound) - 5, 8),
            [e.txn_id for e in inbound],
        ))

    combined = 1.0
    for r in reasons:
        combined *= 1 - r.strength
    return 1 - combined, reasons, has_history
