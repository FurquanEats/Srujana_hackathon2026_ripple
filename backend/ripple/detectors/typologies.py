"""Typology detectors. Each one looks at the current transaction and the feature store (which already includes it)
and returns a Reason citing the transactions behind it, or None. Thresholds come from the region pack.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

from ripple.features.store import AccountState, Edge, FeatureStore, baseline, window
from ripple.fmt import duration, ids, money, names
from ripple.schema import Layer, Rail, Reason, Transaction

Params = dict[str, Any]
# Accounts receiving more than this many payments in a detector window behave like banks, payment processors or
# large merchants, not mules. Pass-through and fan-in checks skip them: summing their windows on every payment is
# the costliest step at IBM AML scale, and they do not fit the mule pattern anyway.
HUB_LIMIT = 1000


def _reason(code: str, text: str, strength: float, txn_ids: list[str], counterfactual: str | None = None) -> Reason:
    return Reason(
        layer=Layer.DETECTOR,
        code=code,
        text=text,
        strength=round(min(1.0, max(0.0, strength)), 3),
        txn_ids=list(dict.fromkeys(txn_ids)),
        counterfactual=counterfactual,
    )


def _ramp(value: float, start: float, full: float) -> float:
    """0 at `start`, 1 at `full` and beyond."""
    if full <= start:
        return 1.0
    return min(1.0, max(0.0, (value - start) / (full - start)))


def pass_through(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """Money from new senders sent on within minutes of arriving: the core mule behaviour.

    Requiring new senders keeps a salaried customer who pays rent right after a known employer's salary out of it.
    """
    if txn.rail == Rail.CASH:
        return None
    lookback = timedelta(hours=p["lookback_hours"])
    received = window(src.incoming, txn.ts, lookback)
    if not received or len(received) > HUB_LIMIT:
        return None
    gap = txn.ts - received[-1].ts
    if gap > timedelta(minutes=p["within_minutes"]):
        return None
    inflow = sum(e.amount for e in received)
    if inflow < p["min_inflow"]:  # an alerting floor only; an STR has no minimum amount
        return None
    sent = [e for e in window(src.outgoing, txn.ts, lookback) if e.ts >= received[0].ts]
    outflow = sum(e.amount for e in sent)
    ratio = outflow / inflow
    if not p["forward_share"] <= ratio <= 1.2:  # forwarding far more than received means the account had its own funds
        return None
    cutoff = txn.ts - lookback
    new_share = sum(e.amount for e in received if src.senders.get(e.counterparty, cutoff) >= cutoff) / inflow
    if new_share < p["min_new_sender_share"]:
        return None
    senders = {e.counterparty for e in received}
    new_senders = {c for c in senders if src.senders.get(c, cutoff) >= cutoff}
    from_new = [e for e in received if e.counterparty in new_senders]
    strength = 0.6 + 0.2 * _ramp(ratio, p["forward_share"], 1.0) + 0.1 * (1 - gap / timedelta(minutes=p["within_minutes"])) + 0.1 * new_share
    return _reason(
        "pass_through",
        f"{txn.src_account} received {money(inflow, txn.currency)} from {len(senders)} sender{'s' if len(senders) > 1 else ''}, "
        f"{len(new_senders)} of them new "
        f"({ids([e.txn_id for e in received])}) and sent {min(ratio, 1.0):.0%} of it onward {duration(gap)} after "
        f"the last one arrived ({ids([e.txn_id for e in sent])})",
        strength,
        [e.txn_id for e in from_new] + [e.txn_id for e in sent],
        f"Not flagged if less than {p['forward_share']:.0%} had been sent on, or if it had left more than "
        f"{p['within_minutes']} minutes after arriving",
    )


def fan_in_out(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """Many first-time senders into one account, which then empties it: a collection account.

    Counting only senders who never paid the account before keeps regular relationships (family, employer, repeat
    customers) from adding up to an alert. The burst of new senders must also be at least twice the account's usual
    daily rate of new senders, so a shop that gains new customers every day is not a collection account, and the
    outflow must be close to the inflow: a shop paying its supplier many times what customers paid it today is
    spending its own money, not passing someone else's along.
    """
    if txn.rail == Rail.CASH:
        return None
    span = timedelta(hours=p["window_hours"])
    cutoff = txn.ts - span
    received = window(src.incoming, txn.ts, span)
    if len(received) > HUB_LIMIT:
        return None
    senders = {e.counterparty for e in received if src.senders.get(e.counterparty, cutoff) >= cutoff}
    if len(senders) < p["min_senders"]:
        return None
    known_days = max((cutoff - src.first_seen).total_seconds() / 86400, 1.0)
    usual = (len(src.senders) - len(senders)) / known_days  # new senders on a typical day
    if len(senders) < 2 * usual:
        return None
    inflow = sum(e.amount for e in received)
    sent = [e for e in window(src.outgoing, txn.ts, span) if e.ts >= received[0].ts]
    ratio = sum(e.amount for e in sent) / inflow
    if not p["min_outflow_share"] <= ratio <= 1.2:
        return None
    strength = 0.6 + 0.25 * _ramp(len(senders), p["min_senders"], p["min_senders"] + 5) + 0.15 * _ramp(ratio, p["min_outflow_share"], 1.0)
    return _reason(
        "fan_in_out",
        f"{len(senders)} first-time senders paid {txn.src_account}, {money(inflow, txn.currency)} in total within {duration(received[-1].ts - received[0].ts)}, "
        f"then {txn.src_account} moved {min(ratio, 1.0):.0%} of it out",
        strength,
        [e.txn_id for e in received if e.counterparty in senders] + [e.txn_id for e in sent],
        f"Not flagged if fewer than {p['min_senders']} first-time senders had paid {txn.src_account} within {p['window_hours']} hours",
    )


def fan_out_burst(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """Many first-time payees in a short burst, well above the account's own usual rate of new payees: typical of
    scam proceeds being dispersed, or a takeover. A business that always pays new payees does not trigger it."""
    if txn.rail == Rail.CASH:
        return None
    span = timedelta(minutes=p["window_minutes"])
    cutoff = txn.ts - span
    fresh = [e for e in window(src.outgoing, txn.ts, span) if src.payees.get(e.counterparty, txn.ts) >= cutoff]
    payees = list(dict.fromkeys(e.counterparty for e in fresh))
    if len(payees) < p["min_new_payees"]:
        return None
    if not window(src.incoming, txn.ts, timedelta(hours=72)) and src.first_seen >= cutoff:
        return None  # an account with no history paying out money it was never seen receiving: nothing to judge against
    known_days = max((cutoff - src.first_seen).total_seconds() / 86400, 1.0)
    usual = (len(src.payees) - len(payees)) / known_days  # new payees on a typical day
    if len(payees) < 2 * usual:  # a business that adds this many payees most days, even in one batch, is normal
        return None
    paid_out = sum(e.amount for e in fresh)
    day = txn.ts - timedelta(hours=24)
    fresh_in = [e for e in window(src.incoming, txn.ts, timedelta(hours=24)) if src.senders.get(e.counterparty, day) >= day]
    funded = sum(e.amount for e in fresh_in) >= 0.7 * paid_out  # dispersing money a stranger sent within the day
    strength = 0.55 + 0.35 * _ramp(len(payees), p["min_new_payees"], p["min_new_payees"] + 5) + 0.15 * funded
    funding = f", mostly money that arrived from a new sender in the last day ({ids([e.txn_id for e in fresh_in])})" if funded else ""
    return _reason(
        "fan_out_burst",
        f"{txn.src_account} paid {len(payees)} first-time payees {money(paid_out, txn.currency)} "
        f"in {duration(txn.ts - fresh[0].ts)}, against a usual {usual:.1f} new payees a day{funding}",
        strength,
        ([e.txn_id for e in fresh_in] if funded else []) + [e.txn_id for e in fresh],
        f"Not flagged if fewer than {p['min_new_payees']} new payees had been paid within {p['window_minutes']} minutes",
    )


def scatter_gather(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """Funds split across several intermediaries that recombine at one account.

    Each intermediary must pass on at least `min_pass_share` of what it received from the origin; the gathering
    account must not be a merchant taking payments from many people; and the origin must be an account that paid
    the intermediaries itself (not cash banked over the counter) and paid no more than `max_origin_payees` people in
    the window. Without these checks, an employer or gig platform paying people who later shop at the same store, or
    shops banking cash and paying one supplier, look exactly like this pattern.
    """
    if txn.rail == Rail.CASH:
        return None
    span = timedelta(hours=p["window_hours"])
    gathered = window(dst.incoming, txn.ts, span)
    if len(gathered) > 200 or len({e.counterparty for e in gathered}) > p["max_gather_senders"]:
        return None  # a merchant: many different people pay it
    legs: dict[str, list[tuple[Edge, Edge]]] = {}  # origin -> [(origin->intermediary, intermediary->dst)]
    for out_leg in gathered:
        mid = store.get(out_leg.counterparty)
        if mid is None or out_leg.counterparty == txn.dst_account:
            continue
        for in_leg in window(mid.incoming, out_leg.ts, span):
            if (in_leg.ts <= out_leg.ts and in_leg.counterparty not in (txn.dst_account, out_leg.counterparty)
                    and out_leg.amount >= p["min_pass_share"] * in_leg.amount):
                legs.setdefault(in_leg.counterparty, []).append((in_leg, out_leg))
    best = None
    for origin, pairs in legs.items():
        mids = {o.counterparty for _, o in pairs}
        if len(mids) < p["min_intermediaries"] or txn.src_account not in mids:
            continue
        origin_state = store.get(origin)
        paid = {e.counterparty for e in window(origin_state.outgoing, txn.ts, span)} if origin_state else set()
        if not mids <= paid or len(paid) > p["max_origin_payees"]:
            continue  # cash banked over the counter, or a payroll-like payer
        if best is None or len(mids) > len(best[1]):
            best = (origin, mids, pairs)
    if best is None:
        return None
    origin, mids, pairs = best
    first = min(i.ts for i, _ in pairs)
    sent = sum(i.amount for i, _ in {i.txn_id: (i, o) for i, o in pairs}.values())
    strength = 0.65 + 0.25 * _ramp(len(mids), p["min_intermediaries"], p["min_intermediaries"] + 3)
    return _reason(
        "scatter_gather",
        f"{money(sent, txn.currency)} left {origin} through {len(mids)} accounts ({names(sorted(mids))}) and reached "
        f"{txn.dst_account} within {duration(txn.ts - first)}",
        strength,
        [i.txn_id for i, _ in pairs] + [o.txn_id for _, o in pairs],
        f"Not flagged if the funds had passed through fewer than {p['min_intermediaries']} accounts",
    )


def temporal_cycle(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """Money that returns to where it started through a time-ordered chain of 3 or more accounts."""
    if txn.rail == Rail.CASH or txn.src_account == txn.dst_account:
        return None
    origin, closer = txn.dst_account, txn.src_account
    start = txn.ts - timedelta(hours=p["window_hours"])
    max_edges = p["max_hops"] - 1  # the current transaction is the last hop
    found: list[Edge] | None = None
    budget = [500]  # accounts the search may visit for one transaction, so busy hubs stay cheap

    def walk(account: str, after, path: list[Edge], seen: set[str]) -> None:
        nonlocal found
        if found is not None or len(path) >= max_edges or budget[0] <= 0:
            return
        budget[0] -= 1
        state = store.get(account)
        if state is None:
            return
        for edge in list(state.outgoing)[-25:]:  # cap the branching on busy accounts
            if edge.ts < after or edge.ts > txn.ts or edge.txn_id == txn.txn_id:
                continue
            if edge.counterparty == closer and len(path) >= 1:
                found = path + [edge]
                return
            if edge.counterparty not in seen and edge.counterparty != origin:
                walk(edge.counterparty, edge.ts, path + [edge], seen | {edge.counterparty})
            if found is not None:
                return

    walk(origin, start, [], {origin})
    if found is None:
        return None
    hops = found + [Edge(txn.txn_id, txn.ts, origin, txn.amount)]
    similar = 0.5 <= txn.amount / found[0].amount <= 1.1
    strength = 0.7 + 0.2 * similar + 0.1 * (1 - (len(hops) - 3) / max(1, p["max_hops"] - 3))
    via = [e.counterparty for e in found]
    return _reason(
        "temporal_cycle",
        f"{money(found[0].amount, txn.currency)} left {origin} and {money(txn.amount, txn.currency)} came back via {names(via)} "
        f"within {duration(txn.ts - found[0].ts)}",
        strength,
        [e.txn_id for e in hops],
        f"Not flagged if the money had taken longer than {p['window_hours']} hours or more than {p['max_hops']} hops to return",
    )


def cash_structuring(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """Repeated cash deposits kept just under the Rs 50,000 a day at which PAN must be quoted."""
    if txn.rail != Rail.CASH or not p["band_low"] <= txn.amount <= p["band_high"]:
        return None
    recent = window(dst.cash_deposits, txn.ts, timedelta(days=p["window_days"]))
    banded = [e for e in recent if p["band_low"] <= e.amount <= p["band_high"]]
    if len(banded) < p["min_deposits"]:
        return None
    tight = sum(1 for e in banded if e.amount >= p["band_high"] - 1000) / len(banded)
    strength = 0.75 + 0.15 * _ramp(len(banded), p["min_deposits"], p["min_deposits"] + 3) + 0.1 * tight
    low, high = min(e.amount for e in banded), max(e.amount for e in banded)
    return _reason(
        "cash_structuring",
        f"{len(banded)} cash deposits of {money(low, txn.currency)} to {money(high, txn.currency)} into {txn.dst_account} in "
        f"{duration(txn.ts - banded[0].ts)}, each just below the {money(p['band_high'], txn.currency)} {p['limit_label']}",
        strength,
        [e.txn_id for e in banded],
        f"Not flagged if fewer than {p['min_deposits']} deposits between {money(p['band_low'], txn.currency)} and "
        f"{money(p['band_high'], txn.currency)} had been made within {p['window_days']} days",
    )


def ctr_reportable(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """Cash this calendar month above the CTR limit. A reporting fact, not suspicion, so its strength is low."""
    if txn.rail != Rail.CASH or p.get("ctr_monthly_limit") is None:
        return None
    month = [e for e in dst.cash_deposits if (e.ts.year, e.ts.month) == (txn.ts.year, txn.ts.month)]
    total = sum(e.amount for e in month)
    if total <= p["ctr_monthly_limit"] or total - txn.amount > p["ctr_monthly_limit"]:
        return None  # report once, on the deposit that crosses the limit
    return _reason(
        "ctr_reportable",
        f"Cash into {txn.dst_account} this month reached {money(total, txn.currency)} over {len(month)} deposits, above the "
        f"{money(p['ctr_monthly_limit'], txn.currency)} CTR limit for integrally connected cash transactions",
        0.3,
        [e.txn_id for e in month],
    )


def device_takeover(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, p: Params) -> Reason | None:
    """A new device followed quickly by the account's largest-ever payment to a new payee, as after a SIM swap."""
    if txn.rail == Rail.CASH or not txn.device_id:
        return None
    first_use = src.devices.get(txn.device_id)
    older = [d for d, seen in src.devices.items() if seen < (first_use or txn.ts)]
    if first_use is None or not older or txn.ts - first_use > timedelta(minutes=p["window_minutes"]):
        return None
    b = baseline(src)
    if txn.amount <= src.max_out_amount or (b is not None and txn.amount < 3 * b.median):
        return None
    new_payee = src.payees.get(txn.dst_account) == txn.ts
    strength = 0.75 + 0.15 * new_payee + 0.1 * (1 - (txn.ts - first_use) / timedelta(minutes=p["window_minutes"]))
    return _reason(
        "device_takeover",
        f"New device {txn.device_id} first used at {first_use:%H:%M}, then {money(txn.amount, txn.currency)} to "
        f"{'first-time payee ' if new_payee else ''}{txn.dst_account} at {txn.ts:%H:%M}, the largest payment "
        f"{txn.src_account} has made",
        strength,
        [txn.txn_id],
        f"Not flagged if the device had been in use for more than {p['window_minutes']} minutes before this payment",
    )


Detector = Callable[[Transaction, FeatureStore, AccountState, AccountState, Params], Reason | None]

DETECTORS: dict[str, Detector] = {
    "pass_through": pass_through,
    "fan_in_out": fan_in_out,
    "fan_out_burst": fan_out_burst,
    "scatter_gather": scatter_gather,
    "temporal_cycle": temporal_cycle,
    "cash_structuring": cash_structuring,
    "device_takeover": device_takeover,
}


def run(txn: Transaction, store: FeatureStore, src: AccountState, dst: AccountState, pack: dict[str, Any]) -> list[Reason]:
    params = pack["detectors"]
    reasons = [fn(txn, store, src, dst, params[name]) for name, fn in DETECTORS.items() if name in params]
    reasons.append(ctr_reportable(txn, store, src, dst, params["cash_structuring"]))
    return [r for r in reasons if r is not None]
