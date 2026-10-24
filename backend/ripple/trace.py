"""Golden-hour trace: from a victim's report, follow the money forward through every hop the bank can see.

Starting from the victim's account and the time of the reported payment, the trace takes each payment the victim
made to a payee they had never paid before (or the payments closest to a reported amount), and
then each payment the receiving account made after the money arrived, breadth first, up to `max_hops` hops and
`window` after the report. The trail it finds goes through the same taint tracking and minimum-cut freeze plan as an
alerted case (ripple.interdiction), so the officer sees where the money sits now and which accounts to freeze.

The trace follows timing, not labels: an account that received the victim's money and then paid someone else is
assumed to have passed some of it on, in proportion to what it held (the haircut rule). It can only see accounts in
the engine's recent window (72 hours), which is the golden hour that matters for recovery anyway.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from ripple.cash import is_cash_deposit
from ripple.engine import Engine
from ripple.interdiction import plan_trail
from ripple.schema import InterdictionPlan, ScoredTransaction

MAX_TXNS = 400
MERCHANT_SENDERS = 20  # an account paid by more distinct people than this is a merchant, not a scam account


def _merchant(engine: Engine, account: str) -> bool:
    state = engine.store.get(account)
    return state is not None and len(state.senders) > MERCHANT_SENDERS


def onward(engine: Engine, trail: list[ScoredTransaction], max_hops: int = 3) -> list[ScoredTransaction]:
    """Payments that accounts on a trail made after receiving money on it: where the money went next, including
    withdrawals and crypto purchases that happened after the last alert."""
    received: dict[str, datetime] = {}
    for t in trail:
        if t.dst_account not in received or t.ts < received[t.dst_account]:
            received[t.dst_account] = t.ts
    seen = {t.txn_id for t in trail}
    found: list[ScoredTransaction] = []
    frontier = list(received.items())
    for _ in range(max_hops):
        nxt: list[tuple[str, datetime]] = []
        for account, since in frontier:
            state = engine.store.get(account)
            if state is None or _merchant(engine, account):
                continue
            for edge in state.outgoing:
                if edge.ts >= since and edge.txn_id not in seen and (txn := engine.lookup(edge.txn_id)) is not None:
                    seen.add(edge.txn_id)
                    found.append(txn)
                    nxt.append((edge.counterparty, edge.ts))
        frontier = nxt
        if len(found) > MAX_TXNS:
            break
    return found


def trace(engine: Engine, account: str, from_ts: datetime, amount: float | None = None, max_hops: int = 6,
          window: timedelta = timedelta(hours=72)) -> InterdictionPlan | None:
    start = engine.store.get(account)
    if start is None:
        return None
    first_hop = [e for e in start.outgoing if e.ts >= from_ts]
    if amount is not None:  # the report names an amount: start from the payments closest to it
        first_hop = sorted(first_hop, key=lambda e: abs(e.amount - amount))[:3]
    else:  # scam transfers go to new payees who are not merchants; ordinary spending at shops is left out
        first_hop = [e for e in first_hop if start.payees.get(e.counterparty, from_ts) >= from_ts
                     and not _merchant(engine, e.counterparty)]
    trail: dict[str, ScoredTransaction] = {}
    queue = deque((e, 1) for e in sorted(first_hop, key=lambda e: e.ts))
    end = from_ts + window
    while queue and len(trail) < MAX_TXNS:
        edge, hop = queue.popleft()
        if edge.txn_id in trail or edge.ts > end:
            continue
        txn = engine.lookup(edge.txn_id)
        if txn is None or is_cash_deposit(txn):
            continue
        trail[edge.txn_id] = txn
        holder = engine.store.get(edge.counterparty)
        if holder is None or hop >= max_hops:
            continue
        for onward in holder.outgoing:
            if onward.ts >= edge.ts and onward.txn_id not in trail and onward.counterparty != account:
                queue.append((onward, hop + 1))
    if not trail:
        return None
    accounts = {t.dst_account for t in trail.values()} - {account}
    profiles = [p for p in (engine._profile(a) for a in sorted(accounts)) if p]
    return plan_trail(f"trace-{account}", list(trail.values()), profiles, engine.store.now)
