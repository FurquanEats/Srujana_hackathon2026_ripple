"""Interdiction: where is the stolen money now, and which accounts should be frozen to recover the most of it?

Taint tracking follows the money in a case's trail in time order with the haircut method used in crypto forensics:
when an account holding a mix of traced and other funds sends money on, each rupee it sends carries the same traced
share as its holdings. Money enters the trail from outside (the victims' payments, or cash deposits) and leaves it
when a holder pays an account outside the trail.

The freeze set is a minimum cut. Each holder is a node whose capacity is its collateral cost (how much ordinary
activity a freeze would disrupt); traced money starts at every holder that has some, and must not reach an exit
(a payment out of the trail, or a collector, which is where mule money is cashed out). The cheapest set of holders
that separates the two blocks every observed path out. Holders sitting on a large share of the traced money are
added even when the cut does not need them, because freezing them recovers money directly.

Only evidence counts: alerted transactions and the transactions their detector reasons cite. Other payments around
the case (a mule's ordinary daily income, say) are not traced. A closed loop such as a cycle has no outside entry,
so its first payment is where the traced money starts.

The trail only shows what the bank can see; an account's own funds from before the trail are unknown, so held
amounts are what flowed in minus what flowed out, never below zero. A holder's other payments in (`own_funds`: its
salary, say, within the engine's window) are its own money mixed in with the traced money.

Once traced and own money are mixed, which rupees left is a convention, and accepted conventions disagree. Every
holder's traced balance is therefore computed under three rules over the same payments, and each freeze shows the
range they give:

- haircut (pro rata): every rupee sent carries the account's traced share at that moment;
- FIFO (first in, first out): money leaves in the order it arrived;
- LIBR (lowest intermediate balance): the account's own money is spent first, so traced money stays as long as the
  balance allows; once the balance dips, later deposits never refill what was traced.

Money an account sends beyond everything seen coming in is its own earlier money under every rule. The haircut figure
drives the freeze set, the timeline and "recoverable now"; the lowest of the three is the amount every rule supports.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from ripple.cash import is_cash_deposit, is_cash_out
from ripple.fmt import money
from ripple.schema import (
    AccountProfile,
    CaseDetail,
    FreezeAction,
    GraphEdge,
    InterdictionPlan,
    Layer,
    RecoveryPoint,
    ScoredTransaction,
    TaintHolding,
)

DIRECT_FREEZE_SHARE = 0.05  # freeze any holder sitting on at least this share of the traced money
EXIT = "__exit__"
RULES = ("haircut", "fifo", "libr")
OwnFunds = Sequence[tuple[datetime, str, float, str]]  # (time, holder, amount, txn id) paid in from outside the trail
SOURCE = "__source__"


@dataclass
class _Account:
    received: float = 0.0
    sent: float = 0.0
    held: float = 0.0
    tainted: float = 0.0


def plan(detail: CaseDetail, as_of: datetime | None = None, onward: list[ScoredTransaction] = (),
         own_funds: OwnFunds = ()) -> InterdictionPlan:
    """Freeze plan for a case, tracing its evidence (alerts and the transactions their detector reasons cite) plus any
    `onward` payments its holders made later, such as a cash withdrawal after the last alert.

    A coerced customer is the victim, not a holder: the lump sum that funded their transfer (a broken fixed deposit,
    say) is their own money, so it is left out and their transfers to the scammers become where stolen money starts.
    """
    evidence = {t.txn_id for t in detail.timeline if t.is_alert}
    coerced = set()
    for t in detail.timeline:
        if t.is_alert:
            evidence.update(i for r in t.reasons if r.layer == Layer.DETECTOR for i in r.txn_ids)
            if any(r.code == "coerced_transfer" for r in t.reasons):
                coerced.add(t.src_account)
    trail = [t for t in detail.timeline if t.txn_id in evidence and t.dst_account not in coerced]
    seen = {t.txn_id for t in trail}
    trail += [t for t in onward if t.txn_id not in seen and t.dst_account not in coerced]
    end = as_of or (max(t.ts for t in trail) if trail else detail.updated_at)
    return plan_trail(detail.case_id, trail, detail.profiles, end, own_funds)


def plan_trail(case_id: str, trail: list[ScoredTransaction], profiles: list[AccountProfile],
               as_of: datetime | None = None, own_funds: OwnFunds = ()) -> InterdictionPlan:
    """Freeze plan for any money trail: a case's evidence, or the hops followed forward from a victim's report."""
    txns = sorted(trail, key=lambda t: t.ts)
    as_of = as_of or (txns[-1].ts if txns else datetime.now())
    txns = [t for t in txns if t.ts <= as_of]
    # Roles come from the evidence alone: whoever receives traced money holds it; whoever only sends is a source.
    holders = {t.dst_account for t in txns if not is_cash_out(t)}
    senders = {t.src_account for t in txns if not is_cash_deposit(t)}
    entries = [t for t in txns if (t.src_account not in holders or is_cash_deposit(t)) and t.dst_account in holders]
    if not entries and txns:  # a closed loop such as a cycle: the money starts with the first payment
        holders.add(txns[0].dst_account)
        entries = [txns[0]]
    entry_ids = {t.txn_id for t in entries}

    accounts = {a: _Account() for a in holders}
    entered_at_alert = None
    exits: set[str] = set()
    stolen = escaped = 0.0
    victims: list[str] = []
    timeline: list[RecoveryPoint] = []
    first_alert = next((t.ts for t in txns if t.is_alert), None)
    recoverable_at_first_alert = None
    on_trail = {t.txn_id for t in txns}
    own = sorted((f for f in own_funds if f[1] in holders and f[0] <= as_of and f[3] not in on_trail),
                 key=lambda f: f[0])
    events = _merge(txns, own)

    for t in events:
        if isinstance(t, tuple):  # a holder's own money arriving: it dilutes the traced share
            accounts[t[1]].held += t[2]
            continue
        dst = accounts.get(t.dst_account)
        if t.txn_id in entry_ids:
            stolen += t.amount
            victims.append("cash deposits" if is_cash_deposit(t) else t.src_account)
            dst.received += t.amount
            dst.held += t.amount
            dst.tainted += t.amount
        elif t.src_account in accounts and not is_cash_deposit(t):
            src = accounts[t.src_account]
            share = src.tainted / src.held if src.held > 0 else 0.0
            moved = min(src.tainted, t.amount * share)
            src.tainted -= moved
            src.held = max(0.0, src.held - t.amount)
            src.sent += t.amount
            if dst is not None:
                dst.received += t.amount
                dst.held += t.amount
                dst.tainted += moved
            else:
                escaped += moved
                exits.add(t.src_account)
        else:
            continue
        recoverable = sum(a.tainted for a in accounts.values())
        timeline.append(RecoveryPoint(ts=t.ts, recoverable=round(recoverable, 2), escaped=round(escaped, 2)))
        if first_alert is not None and recoverable_at_first_alert is None and t.ts >= first_alert:
            recoverable_at_first_alert = round(recoverable, 2)
            entered_at_alert = stolen

    profiles = {p.account_id: p for p in profiles}
    costs = {a: _collateral_cost(profiles.get(a)) for a in accounts}
    collectors = holders - senders
    cut = _minimum_cut(txns, accounts, costs, exits | collectors)
    freeze_ids = set(cut) | {a for a, s in accounts.items() if stolen and s.tainted >= DIRECT_FREEZE_SHARE * stolen}

    currency = txns[0].currency if txns else "INR"
    by_rule = _taint_by_rule(events, holders, entry_ids)
    freeze = sorted(
        (FreezeAction(
            account_id=a,
            recoverable=round(accounts[a].tainted, 2),
            collateral_cost=round(costs[a], 2),
            reason=_reason(a, accounts[a].tainted, a in cut, a in collectors, currency),
            by_rule={r: round(v, 2) for r, v in by_rule[a].items()},
            hold_low=round(min(by_rule[a].values()), 2),
            hold_high=round(max(by_rule[a].values()), 2),
        ) for a in freeze_ids),
        key=lambda f: -f.recoverable,
    )
    holdings = sorted(
        (TaintHolding(
            account_id=a,
            received=round(s.received, 2),
            sent=round(s.sent, 2),
            tainted=round(s.tainted, 2),
            tainted_share=round(min(1.0, s.tainted / s.held), 4) if s.held > 0 else 0.0,
        ) for a, s in accounts.items()),
        key=lambda h: -h.tainted,
    )
    return InterdictionPlan(
        case_id=case_id,
        as_of=as_of,
        stolen=round(stolen, 2),
        victims=list(dict.fromkeys(victims)),
        holdings=holdings,
        freeze=freeze,
        recoverable_now=round(sum(f.recoverable for f in freeze), 2),
        recoverable_low=round(sum(f.hold_low for f in freeze), 2),
        recoverable_high=round(sum(f.hold_high for f in freeze), 2),
        escaped=round(escaped, 2),
        first_alert_at=first_alert,
        recoverable_at_first_alert=recoverable_at_first_alert,
        recoverable_share_at_first_alert=round(recoverable_at_first_alert / entered_at_alert, 4)
        if recoverable_at_first_alert is not None and entered_at_alert else None,
        timeline=timeline,
        edges=[GraphEdge(txn_id=t.txn_id, source=t.src_account, target=t.dst_account, amount=t.amount, ts=t.ts)
               for t in txns],
        method="haircut taint tracking over the case's money trail, with FIFO and lowest-intermediate-balance figures "
        "for each hold; freeze set = minimum vertex cut weighted by collateral cost, plus any holder with at least 5% "
        "of the traced money",
    )


def _merge(txns: list[ScoredTransaction], own: list[tuple[datetime, str, float, str]]) -> list:
    """Trail payments and own-money arrivals in one time order; at equal times own money arrives first."""
    out, i = [], 0
    for t in txns:
        while i < len(own) and own[i][0] <= t.ts:
            out.append(own[i])
            i += 1
        out.append(t)
    return out + own[i:]


def _taint_by_rule(events: list, holders: set[str], entry_ids: set[str]) -> dict[str, dict[str, float]]:
    """Traced money each holder still holds at the end, under each rule in RULES.

    Each account keeps its money as lots of (amount, traced amount) in arrival order. Haircut and LIBR only need the
    totals; FIFO spends the lots oldest first. A payment carries its traced part onward to the next holder, so the
    rules can disagree more with every hop.
    """
    held: dict[str, dict[str, float]] = {a: {} for a in holders}
    for rule in RULES:
        lots: dict[str, list[list[float]]] = {a: [] for a in holders}
        for e in events:
            if isinstance(e, tuple):
                lots[e[1]].append([e[2], 0.0])
                continue
            dst = lots.get(e.dst_account)
            if e.txn_id in entry_ids:
                dst.append([e.amount, e.amount])
                continue
            if e.src_account not in lots or is_cash_deposit(e):
                continue
            traced = _spend(lots[e.src_account], e.amount, rule)
            if dst is not None:
                dst.append([e.amount, traced])
        for a in holders:
            held[a][rule] = sum(lot[1] for lot in lots[a])
    return held


def _spend(lots: list[list[float]], amount: float, rule: str) -> float:
    """Removes `amount` from an account's lots under `rule` and returns the traced part of what left. Anything beyond
    what was seen coming in is the account's own earlier money and carries nothing traced."""
    total = sum(lot[0] for lot in lots)
    traced = sum(lot[1] for lot in lots)
    out = min(amount, total)
    if out <= 0:
        return 0.0
    if rule == "haircut":
        keep = 1 - out / total
        for lot in lots:
            lot[0] *= keep
            lot[1] *= keep
        return traced * out / total
    if rule == "libr":  # own money first, then traced
        from_traced = max(0.0, out - (total - traced))
        lots[:] = [[total - out, traced - from_traced]]
        return from_traced
    moved = 0.0  # fifo
    while out > 1e-9 and lots:
        lot = lots[0]
        take = min(out, lot[0])
        part = lot[1] * take / lot[0] if lot[0] else 0.0
        lot[0] -= take
        lot[1] -= part
        moved += part
        out -= take
        if lot[0] <= 1e-9:
            lots.pop(0)
    return moved


def _collateral_cost(profile: AccountProfile | None) -> float:
    """1 for a fresh account with no ordinary activity, rising with its payment history and age."""
    if profile is None:
        return 1.0
    activity = math.log1p(profile.txns_30d or 0)
    age = 1.0 if (profile.opened_days_ago or 0) > 180 else 0.0
    return round(1.0 + activity / 2 + age, 2)


def _minimum_cut(txns: list[ScoredTransaction], accounts: dict[str, _Account], costs: dict[str, float],
                 exits: set[str]) -> list[str]:
    """Holders to freeze so no traced money can reach an exit, at the lowest total collateral cost.

    Each holder is split into an in-node and an out-node joined by an edge whose capacity is its cost, so cutting
    that edge means freezing the account. Payment edges and the source and exit links have no capacity limit.
    """
    holding = [a for a, s in accounts.items() if s.tainted > 0]
    if not holding or not exits:
        return []
    g = nx.DiGraph()
    for a in accounts:
        g.add_edge(("in", a), ("out", a), capacity=costs[a])
    for t in txns:
        if t.src_account in accounts and t.dst_account in accounts and not is_cash_deposit(t):
            g.add_edge(("out", t.src_account), ("in", t.dst_account))
    for a in holding:
        g.add_edge(SOURCE, ("in", a))
    for a in exits & set(accounts):
        g.add_edge(("out", a), EXIT)
    if not g.has_node(EXIT):
        return []
    _, (reachable, _) = nx.minimum_cut(g, SOURCE, EXIT)
    return sorted(a for a in accounts if ("in", a) in reachable and ("out", a) not in reachable)


def _reason(account: str, tainted: float, in_cut: bool, collector: bool, currency: str) -> str:
    parts = []
    if tainted > 0:
        parts.append(f"holds {money(tainted, currency)} traceable to the victims' payments")
    if in_cut:
        parts.append("sits on every observed path from the traced money to cash-out")
    if collector:
        parts.append("receives from the mules and is where the money would be cashed out")
    text = "; ".join(parts) or "on the money trail"
    return f"{account} {text}"
