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


def trace(engine: Engine, account: str, from_ts: datetime, amount: float | None = None, max_hops: int = 6,
          window: timedelta = timedelta(hours=72)) -> InterdictionPlan | None:
    start = engine.store.get(account)
    if start is None:
        return None
    first_hop = [e for e in start.outgoing if e.ts >= from_ts]
    if amount is not None:  # the report names an amount: start from the payments closest to it
        first_hop = sorted(first_hop, key=lambda e: abs(e.amount - amount))[:3]
    else:  # scam transfers go to payees the victim never paid before; ordinary spending at known shops is left out
        first_hop = [e for e in first_hop if start.payees.get(e.counterparty, from_ts) >= from_ts]
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
