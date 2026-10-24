"""Per-account rolling state, updated once per transaction in time order.

Windows are pruned on every update, so memory per account stays bounded. State uses slotted classes and plain
lists rather than deques, because a dataset like IBM AML has hundreds of thousands of accounts and an empty deque
costs about ten times an empty list. Transactions must arrive in timestamp order; the replay sorts them.
"""

from __future__ import annotations

import math
from bisect import bisect_left
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ripple.schema import Rail, Transaction

EDGE_WINDOW = timedelta(hours=72)  # longest detector window (temporal cycle)
HISTORY_WINDOW = timedelta(days=30)
CASH_WINDOW = timedelta(days=31)
MAX_HISTORY = 500  # cap per account so very busy accounts stay cheap


@dataclass(frozen=True, slots=True)
class Edge:
    txn_id: str
    ts: datetime
    counterparty: str
    amount: float


@dataclass(slots=True)
class AccountState:
    account_id: str
    first_seen: datetime
    incoming: list[Edge] = field(default_factory=list)  # last 72 h, oldest first
    outgoing: list[Edge] = field(default_factory=list)  # last 72 h, oldest first
    out_history: list[tuple[datetime, float]] = field(default_factory=list)  # last 30 days of outgoing amounts
    cash_deposits: list[Edge] = field(default_factory=list)  # last 31 days
    out_hour_counts: list[int] = field(default_factory=lambda: [0] * 24)  # out_history entries per hour of day
    baseline_cache: Baseline | None = None  # last baseline computed, reused until enough new payments arrive
    appends_since_baseline: int = 0
    payees: dict[str, datetime] = field(default_factory=dict)  # first payment to each payee
    senders: dict[str, datetime] = field(default_factory=dict)  # first payment from each sender
    devices: dict[str, datetime] = field(default_factory=dict)  # first use of each device
    max_out_amount: float = 0.0  # largest outgoing amount before the current transaction
    received_total: int = 0  # all incoming payments since first seen, for the account's usual daily rate


class FeatureStore:
    def __init__(self) -> None:
        self.accounts: dict[str, AccountState] = {}
        self.now: datetime | None = None

    def get(self, account_id: str) -> AccountState | None:
        return self.accounts.get(account_id)

    def _state(self, account_id: str, ts: datetime) -> AccountState:
        state = self.accounts.get(account_id)
        if state is None:
            state = self.accounts[account_id] = AccountState(account_id=account_id, first_seen=ts)
        return state

    def update(self, txn: Transaction) -> tuple[AccountState, AccountState]:
        """Adds the transaction to both accounts' state and returns (source, destination) state.

        Detectors read the state after this call, so windows include the current transaction.
        `max_out_amount` and the payee and device first-seen times are recorded before it is added,
        so "first-time payee" and "new device" checks still work.
        """
        ts = txn.ts
        self.now = ts
        src = self._state(txn.src_account, ts)
        dst = self._state(txn.dst_account, ts)
        for state in (src, dst):
            _prune(state, ts)

        if txn.rail == Rail.CASH:
            dst.cash_deposits.append(Edge(txn.txn_id, ts, txn.src_account, txn.amount))
        else:
            src.outgoing.append(Edge(txn.txn_id, ts, txn.dst_account, txn.amount))
            src.out_history.append((ts, txn.amount))
            src.out_hour_counts[ts.hour] += 1
            src.appends_since_baseline += 1
            if len(src.out_history) > MAX_HISTORY:
                src.out_hour_counts[src.out_history[0][0].hour] -= 1
                del src.out_history[0]
            src.payees.setdefault(txn.dst_account, ts)
            if txn.device_id:
                src.devices.setdefault(txn.device_id, ts)
        dst.incoming.append(Edge(txn.txn_id, ts, txn.src_account, txn.amount))
        dst.received_total += 1
        dst.senders.setdefault(txn.src_account, ts)
        return src, dst

    def after_score(self, txn: Transaction) -> None:
        """Records values that must exclude the current transaction while it is scored."""
        src = self.accounts[txn.src_account]
        if txn.rail != Rail.CASH:
            src.max_out_amount = max(src.max_out_amount, txn.amount)


def _prune(state: AccountState, now: datetime) -> None:
    for span, edges in ((EDGE_WINDOW, state.incoming), (EDGE_WINDOW, state.outgoing), (CASH_WINDOW, state.cash_deposits)):
        k = bisect_left(edges, now - span, key=_edge_ts)
        if k:
            del edges[:k]
    k = bisect_left(state.out_history, now - HISTORY_WINDOW, key=_entry_ts)
    if k:
        for ts, _ in state.out_history[:k]:
            state.out_hour_counts[ts.hour] -= 1
        del state.out_history[:k]


def _edge_ts(edge: Edge) -> datetime:
    return edge.ts


def _entry_ts(entry: tuple[datetime, float]) -> datetime:
    return entry[0]


def window(edges: list[Edge], now: datetime, span: timedelta) -> list[Edge]:
    """Edges within `span` before `now`, oldest first. Edges are kept in time order, so this is a binary search."""
    return edges[bisect_left(edges, now - span, key=_edge_ts):]


@dataclass(frozen=True)
class Baseline:
    """Robust statistics of an account's own outgoing payments over the last 30 days, excluding the current one."""

    n: int
    median: float
    mad: float  # median absolute deviation, scaled by 1.4826 to match a standard deviation

    def z(self, amount: float) -> float:
        floor = max(self.mad, 0.1 * self.median, 1.0)  # avoid huge z-scores for accounts that always pay the same
        return (amount - self.median) / floor


def baseline(state: AccountState, skip_last: bool = True) -> Baseline | None:
    """`skip_last` drops the current transaction, which update() has already added for non-cash payments.

    The median and MAD of up to 500 payments are reused until the account has made 5% more payments, because a
    busy account would otherwise recompute them on every payment and the values barely move.
    """
    n = len(state.out_history) - (1 if skip_last else 0)
    if skip_last and state.baseline_cache is not None and state.appends_since_baseline < max(1, n // 20):
        return state.baseline_cache
    result = _baseline(state, skip_last)
    if skip_last:
        state.baseline_cache, state.appends_since_baseline = result, 1
    return result


def _baseline(state: AccountState, skip_last: bool) -> Baseline | None:
    amounts = [a for _, a in state.out_history]
    if skip_last:
        amounts = amounts[:-1]
    if len(amounts) < 2:
        return None
    med = statistics.median(amounts)
    mad = 1.4826 * statistics.median(abs(a - med) for a in amounts)
    return Baseline(n=len(amounts), median=med, mad=mad)


def hour_share(state: AccountState, hour: int, skip_last: bool = True) -> float | None:
    """Share of past outgoing payments made within one hour of `hour`, excluding the current one."""
    counts = state.out_hour_counts
    total = len(state.out_history)
    near = counts[(hour - 1) % 24] + counts[hour] + counts[(hour + 1) % 24]
    if skip_last and total:
        total -= 1
        near -= 1  # the current payment is in its own hour
    if total < 5:
        return None
    return near / total


def feature_vector(txn: Transaction, src: AccountState, dst: AccountState) -> dict[str, float]:
    """Raw behavioural features for the ML model. Training and live scoring must both use this function."""
    ts = txn.ts
    own = txn.rail != Rail.CASH
    b = baseline(src, skip_last=own)
    in_24h = window(dst.incoming, ts, timedelta(hours=24))
    src_in_30m = window(src.incoming, ts, timedelta(minutes=30))
    src_out_30m = window(src.outgoing, ts, timedelta(minutes=30))
    inflow_30m = sum(e.amount for e in src_in_30m)
    share = hour_share(src, ts.hour, skip_last=own)
    return {
        "log_amount": math.log1p(txn.amount),
        "hour": ts.hour,
        "is_cash": float(txn.rail == Rail.CASH),
        "amount_z": b.z(txn.amount) if b else 0.0,
        "history_n": float(b.n) if b else 0.0,
        "hour_share": share if share is not None else -1.0,
        "payee_new": float(src.payees.get(txn.dst_account) == ts),
        "src_age_days": (ts - src.first_seen).total_seconds() / 86400,
        "dst_age_days": (ts - dst.first_seen).total_seconds() / 86400,
        "src_out_1h": float(len(window(src.outgoing, ts, timedelta(hours=1)))),
        "src_in_24h": float(len(window(src.incoming, ts, timedelta(hours=24)))),
        "dst_senders_24h": float(len({e.counterparty for e in in_24h})),
        "src_outflow_ratio_30m": sum(e.amount for e in src_out_30m) / inflow_30m if inflow_30m else 0.0,
        "src_devices": float(len(src.devices)),
        "device_missing": float(txn.device_id is None),
        "location_missing": float(txn.location is None),
    }
