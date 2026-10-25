"""One-shot pattern learning: an officer confirms one money trail that no detector caught, and Ripple turns its shape
into a new live detector, checked against the bank's own traffic before it goes live.

Every payment out of an account that received money in the last 72 hours is a "relay event", described by a few
numbers: how long the money sat before moving on, what share of it moved on, how many senders paid in and how many of
them were new, how many payees it went to, how old the account is, whether it has any spending of its own, how many
relay hops the money had already passed through, and whether this payment is a cash-out.

Learning from one trail:

1. The trail's relay events are the positive examples. The tightest description of them is a box: each feature
   between its smallest and largest value on the trail. That box catches the example and almost nothing else, and it
   would miss the same scam run with other amounts or other timings.
2. The box is then generalised as far as the bank's own history allows, one step at a time, always taking the step
   that adds the fewest matches among ordinary relay events, and stopping when the expected false alarms would exceed
   the budget (by default one every two days). The knobs a criminal turns cheaply between runs (amounts, timings,
   splits, hops) are freed first, because the next run of the same scam will change them. Constraints that ordinary
   traffic satisfies anyway are dropped. What is left is the shortest description of the scam that ordinary
   customers almost never fit, and each remaining constraint is shown with how rare it is on its own.

The resulting motif runs on every payment as one more detector. A match is evidence for the detector layer, so it goes
through the same fusion, case building, freeze planning and analyst feedback as the built-in typologies.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from ripple.cash import is_cash_deposit, is_cash_out
from ripple.fmt import ids, money
from ripple.schema import Layer, Reason, Transaction

LOOKBACK = timedelta(hours=72)
OWN_HISTORY = timedelta(days=30)
HISTORY = timedelta(days=30)  # relay events kept as the background a new motif is checked against
# In the stream's first days every account looks new: no history, only first-time senders. Accounts first seen then
# are treated as established (their real age is unknown), and motifs stay silent until the warm-up is over.
WARMUP = timedelta(days=3)
ESTABLISHED_DAYS = 365.0
HUB_LIMIT = 200  # accounts paid or paying more often than this in the window are payment hubs, not relays
NEW_SHARE_RELAY = 0.5  # an account relays money when most of what came in was from senders it had not seen before
MIN_CONSTRAINTS = 3  # a motif keeps at least this many constraints, so it describes a shape and not one trait

FEATURES = (
    "wait_hours", "span_hours", "pass_share", "senders", "new_sender_share", "payees", "inflow", "age_days",
    "own_payments", "depth", "cash_out",
)
LOG_SCALE = {"wait_hours", "span_hours", "inflow", "age_days"}  # widened by a factor, not a step
SHARES = {"pass_share", "new_sender_share"}
COUNTS = {"senders", "payees", "own_payments", "depth"}
WIDEN_LIMIT = 6  # widening steps per feature
# Knobs a criminal can turn cheaply between runs of the same scam. The rest describes the accounts themselves (age, own
# spending, who pays them), which takes new accounts or months of cover to change.
KNOBS = {"wait_hours", "span_hours", "pass_share", "senders", "payees", "inflow", "depth", "cash_out"}


@dataclass(slots=True)
class _Account:
    first_seen: datetime
    incoming: list[tuple[datetime, str, float, int, str]] = field(default_factory=list)  # ts, sender, amount, depth, txn
    outgoing: list[tuple[datetime, str, float]] = field(default_factory=list)  # last 72 h
    own_out: list[datetime] = field(default_factory=list)  # outgoing payment times, last 30 days, capped
    senders: dict[str, datetime] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RelayEvent:
    txn_id: str
    ts: datetime
    account: str
    values: tuple[float, ...]  # in FEATURES order
    receipts: tuple[str, ...]  # txn ids of the money that came in, for evidence

    def get(self, feature: str) -> float:
        return self.values[FEATURES.index(feature)]


class RelayTracker:
    """Turns the transaction stream into relay events. Training (the background a motif is checked against) and live
    matching both come from this one class, so they cannot drift apart."""

    def __init__(self) -> None:
        self.accounts: dict[str, _Account] = {}
        self.events: deque[RelayEvent] = deque()
        self.by_txn: dict[str, RelayEvent] = {}
        self.started: datetime | None = None
        # Says whether a payment belongs to a case (set by the engine); such events leave the 30-day background but
        # stay available as examples, so an officer can still learn from an old case.
        self.keep: Callable[[str], bool] | None = None

    def _state(self, account: str, ts: datetime) -> _Account:
        state = self.accounts.get(account)
        if state is None:
            state = self.accounts[account] = _Account(first_seen=ts)
        return state

    def observe(self, txn: Transaction) -> RelayEvent | None:
        ts = txn.ts
        if self.started is None:
            self.started = ts
        if txn.src_account == txn.dst_account:
            return None
        dst = self._state(txn.dst_account, ts)
        if is_cash_deposit(txn):
            _prune(dst, ts)
            dst.incoming.append((ts, txn.src_account, txn.amount, 0, txn.txn_id))
            dst.senders.setdefault(txn.src_account, ts)
            return None
        src = self._state(txn.src_account, ts)
        _prune(src, ts)
        _prune(dst, ts)
        hub = len(src.incoming) > HUB_LIMIT or len(src.outgoing) > HUB_LIMIT
        event = self._event(txn, src) if src.incoming and not hub else None
        src.outgoing.append((ts, txn.dst_account, txn.amount))
        src.own_out.append(ts)
        if len(src.own_out) > 200:
            del src.own_out[0]
        depth = int(event.get("depth")) if event is not None and _is_relay(event) else 0
        dst.incoming.append((ts, txn.src_account, txn.amount, depth, txn.txn_id))
        dst.senders.setdefault(txn.src_account, ts)
        if event is not None:
            self.events.append(event)
            self.by_txn[event.txn_id] = event
            while self.events and ts - self.events[0].ts > HISTORY:
                old = self.events.popleft()
                if not (self.keep and self.keep(old.txn_id)):  # a case's own payments stay learnable however old
                    self.by_txn.pop(old.txn_id, None)
        return event

    def _event(self, txn: Transaction, src: _Account) -> RelayEvent:
        ts = txn.ts
        first, last = src.incoming[0][0], src.incoming[-1][0]
        inflow = sum(r[2] for r in src.incoming)
        new = [r for r in src.incoming if src.senders.get(r[1], first) >= ts - LOOKBACK]
        outflow = txn.amount + sum(o[2] for o in src.outgoing if o[0] >= first)
        payees = {o[1] for o in src.outgoing if o[0] >= first} | {txn.dst_account}
        own = bisect_left(src.own_out, first) - bisect_left(src.own_out, first - OWN_HISTORY)
        known_since_start = self.started is not None and src.first_seen < self.started + WARMUP
        age = ESTABLISHED_DAYS if known_since_start else max((first - src.first_seen).total_seconds() / 86400, 0.0)
        new_share = sum(r[2] for r in new) / inflow if inflow else 0.0
        values = (
            (ts - last).total_seconds() / 3600,
            (ts - first).total_seconds() / 3600,
            min(outflow / inflow, 2.0) if inflow else 2.0,
            float(len({r[1] for r in src.incoming})),
            new_share,
            float(len(payees)),
            inflow,
            age,
            float(own),
            float(1 + max(r[3] for r in src.incoming)),
            float(is_cash_out(txn)),
        )
        return RelayEvent(txn.txn_id, ts, txn.src_account, values, tuple(r[4] for r in src.incoming[-12:]))


def _is_relay(event: RelayEvent) -> bool:
    return event.get("new_sender_share") >= NEW_SHARE_RELAY


def _prune(state: _Account, now: datetime) -> None:
    cutoff = now - LOOKBACK
    k = bisect_left(state.incoming, cutoff, key=lambda r: r[0])
    if k:
        del state.incoming[:k]
    k = bisect_left(state.outgoing, cutoff, key=lambda r: r[0])
    if k:
        del state.outgoing[:k]
    k = bisect_left(state.own_out, now - OWN_HISTORY)
    if k:
        del state.own_out[:k]


# ---- motifs -------------------------------------------------------------------------------------------------------


@dataclass
class Constraint:
    feature: str
    lo: float
    hi: float
    background_share: float = 1.0  # share of ordinary relay events that satisfy this constraint on its own

    def describe(self) -> str:
        return _describe(self.feature, self.lo, self.hi)


@dataclass
class Motif:
    motif_id: str
    name: str
    constraints: list[Constraint]
    learned_from: str  # the case or trace it came from
    example_txn_ids: list[str]
    learned_at: datetime
    background_events: int
    background_days: float
    background_matches: int
    strength: float = 0.85  # detector evidence: with no other layer, a match reaches the Review tier
    deployed: bool = False
    hits: list[str] = field(default_factory=list)  # txn ids matched live since deployment
    lead_hours: float | None = None  # how long before the example's last cash-out the motif would have fired
    steps: list[str] = field(default_factory=list)  # how the description was generalised, for the officer

    @property
    def false_alarms_per_day(self) -> float:
        return self.background_matches / self.background_days if self.background_days else 0.0

    def matches(self, event: RelayEvent) -> bool:
        return all(c.lo <= event.get(c.feature) <= c.hi for c in self.constraints)

    def reason(self, event: RelayEvent, txn: Transaction) -> Reason:
        rules = "; ".join(c.describe() for c in self.constraints)
        return Reason(
            layer=Layer.DETECTOR,
            code=f"motif:{self.motif_id}",
            text=(f"{txn.src_account} matches learned pattern \"{self.name}\" (from {self.learned_from}): {rules}. "
                  f"Money in: {ids(list(event.receipts))}; this payment {money(txn.amount, txn.currency)}."),
            strength=self.strength,
            txn_ids=list(dict.fromkeys([*event.receipts, txn.txn_id])),
            counterfactual=f"Not flagged if any one of these did not hold: {rules}.",
        )


def learn(
    tracker: RelayTracker,
    trail_txn_ids: set[str],
    motif_id: str,
    learned_from: str,
    name: str | None = None,
    max_per_day: float = 0.5,
) -> Motif:
    """Learns a motif from the relay events on one trail, generalised against every other relay event the tracker
    has seen in the last 30 days."""
    positives = [tracker.by_txn[t] for t in trail_txn_ids if t in tracker.by_txn]
    # Only payments by accounts that received money on the trail: the victims' own payments are not the scam's shape.
    positives = [e for e in positives if _is_relay(e) and any(r in trail_txn_ids for r in e.receipts)]
    if not positives:
        raise ValueError("the trail has no account that received money and passed it on, so there is no shape to learn")
    settled = (tracker.started or datetime.min) + WARMUP
    background = [e for e in tracker.events if e.txn_id not in trail_txn_ids and e.ts >= settled]
    X = np.array([e.values for e in background], dtype=float).reshape(-1, len(FEATURES))
    P = np.array([e.values for e in positives], dtype=float)
    days = max((background[-1].ts - background[0].ts).total_seconds() / 86400, 1.0) if background else 1.0
    budget = max_per_day * days

    box = {f: [float(P[:, i].min()), float(P[:, i].max())] for i, f in enumerate(FEATURES)}
    active = set(FEATURES)
    widened = dict.fromkeys(FEATURES, 0)
    steps: list[str] = []

    def count(constraints: dict[str, list[float]], features: set[str]) -> int:
        mask = np.ones(len(X), dtype=bool)
        for f in features:
            i = FEATURES.index(f)
            lo, hi = constraints[f]
            mask &= (X[:, i] >= lo) & (X[:, i] <= hi)
        return int(mask.sum())

    matches = count(box, active)
    if matches > budget:
        raise ValueError(f"even the tightest description of this trail matches {matches} ordinary payments in "
                         f"{days:.0f} days, so it cannot run as a detector without flooding the queue")
    def relax(features: set[str]) -> None:
        """Greedily drops or widens constraints on `features`, cheapest in ordinary matches first, while the total
        stays within budget. On a tie a drop wins, because it covers more variants."""
        nonlocal matches
        while True:
            options = []
            for f in sorted(features & active):
                if len(active) > MIN_CONSTRAINTS:
                    options.append((count(box, active - {f}), 0, f, None))
                if widened[f] < WIDEN_LIMIT and f != "cash_out":
                    wider = _widen(f, *box[f])
                    options.append((count({**box, f: wider}, active), 1, f, wider))
            options = [o for o in options if o[0] <= budget]
            if not options:
                return
            best, _, f, wider = min(options, key=lambda o: (o[0], o[1], widened[o[2]]))
            matches = best
            if wider is None:
                active.discard(f)
                steps.append(f"Freed {_LABEL[f]}: ordinary traffic still matches {best} time{'s' if best != 1 else ''}.")
            else:
                box[f] = wider
                widened[f] += 1

    # 1. Free the knobs a criminal turns cheaply (amounts, timings, splits, hops), as far as the bank's traffic allows.
    relax(KNOBS)
    # 2. Drop what ordinary traffic nearly always satisfies anyway: it says nothing.
    for f in sorted(active):
        if len(active) > MIN_CONSTRAINTS and count(box, {f}) >= 0.95 * len(X) and count(box, active - {f}) <= budget:
            active.discard(f)
            matches = count(box, active)
    # 3. Loosen the structure (account age, own spending, new senders) only with the budget left over.
    relax(set(FEATURES) - KNOBS)
    for f in sorted(active):
        if widened[f]:
            steps.append(f"Widened {_LABEL[f]} to {_describe(f, *box[f])}.")

    constraints = []
    for f in FEATURES:
        if f not in active:
            continue
        lo, hi = box[f]
        share = count(box, {f}) / len(X) if len(X) else 0.0
        constraints.append(Constraint(f, round(lo, 3), round(hi, 3), round(share, 4)))
    constraints.sort(key=lambda c: c.background_share)

    motif = Motif(
        motif_id=motif_id,
        name=name or _name(constraints),
        constraints=constraints,
        learned_from=learned_from,
        example_txn_ids=sorted(trail_txn_ids),
        learned_at=max(e.ts for e in positives),
        background_events=len(X),
        background_days=round(days, 1),
        background_matches=matches,
        steps=steps,
    )
    caught = sorted((e for e in positives if motif.matches(e)), key=lambda e: e.ts)
    cash_outs = sorted(e.ts for e in positives if e.get("cash_out"))
    if caught and cash_outs:  # how long before the last of the example's money was cashed out it would have fired
        motif.lead_hours = round((cash_outs[-1] - caught[0].ts).total_seconds() / 3600, 1)
    return motif


def _widen(feature: str, lo: float, hi: float) -> list[float]:
    if feature in LOG_SCALE:
        return [lo / 1.5, hi * 1.5 if hi > 0 else 1.0]
    if feature in SHARES:
        return [max(lo - 0.1, 0.0), min(hi + 0.1, 2.0)]
    return [max(lo - 1, 0.0), hi + 1]


_LABEL = {
    "wait_hours": "how long the money sat",
    "span_hours": "time from first receipt to this payment",
    "pass_share": "share passed on",
    "senders": "number of senders",
    "new_sender_share": "share from new senders",
    "payees": "number of payees",
    "inflow": "amount received",
    "age_days": "account age when the money arrived",
    "own_payments": "the account's own spending",
    "depth": "hops the money had already passed through",
    "cash_out": "cash-out",
}


def _hours(h: float) -> str:
    return f"{h * 60:.0f} min" if h < 1 else f"{h:.0f} h" if h < 72 else f"{h / 24:.0f} days"


def _describe(feature: str, lo: float, hi: float) -> str:
    n = lambda v: f"{v:.0f}"  # noqa: E731
    match feature:
        case "wait_hours":
            return f"money sat {_hours(lo)} to {_hours(hi)} before moving on"
        case "span_hours":
            return f"paid out {_hours(lo)} to {_hours(hi)} after the first receipt"
        case "pass_share":
            return f"passed on {lo:.0%} to {min(hi, 2.0):.0%} of what came in"
        case "senders":
            return f"{n(lo)} to {n(hi)} senders"
        case "new_sender_share":
            return f"{lo:.0%} to {min(hi, 1.0):.0%} of the money from first-time senders"
        case "payees":
            return f"split across {n(lo)} to {n(hi)} payees"
        case "inflow":
            return f"received {money(lo, 'INR')} to {money(hi, 'INR')}"
        case "age_days":
            return f"account {_hours(lo * 24)} to {_hours(hi * 24)} old when the money arrived"
        case "own_payments":
            return "no spending of its own in the previous 30 days" if hi < 1 else f"{n(lo)} to {n(hi)} own payments in 30 days"
        case "depth":
            return f"money already {n(max(lo - 1, 0))} to {n(hi - 1)} relay hops from the victim"
        case "cash_out":
            if lo >= 1:
                return "the payment is a cash-out"
            return "the payment stays in the banking system" if hi < 1 else "any payment, cash-out or not"
    return f"{feature} {lo}-{hi}"


def _name(constraints: list[Constraint]) -> str:
    by = {c.feature: c for c in constraints}
    words = []
    if "wait_hours" in by and by["wait_hours"].lo >= 6:
        words.append("patient")
    elif "wait_hours" in by and by["wait_hours"].hi <= 1:
        words.append("fast")
    if "age_days" in by and by["age_days"].hi <= 14:
        words.append("new-account")
    if "payees" in by and by["payees"].lo >= 2:
        words.append("splitting")
    name = " ".join([*words, "relay"])
    if "own_payments" in by and by["own_payments"].hi < 1:
        name += " with no spending of its own"
    return name[0].upper() + name[1:]


class MotifLayer:
    """Holds the relay tracker and the learned motifs for one engine."""

    def __init__(self) -> None:
        self.tracker = RelayTracker()
        self.motifs: dict[str, Motif] = {}

    def observe(self, txn: Transaction) -> list[Reason]:
        event = self.tracker.observe(txn)
        if event is None or event.ts < (self.tracker.started or event.ts) + WARMUP:
            return []
        reasons = []
        for motif in self.motifs.values():
            if motif.deployed and motif.matches(event):
                motif.hits.append(txn.txn_id)
                reasons.append(motif.reason(event, txn))
        return reasons

    def learn(self, trail_txn_ids: set[str], learned_from: str, name: str | None = None,
              max_per_day: float = 0.5) -> Motif:
        motif = learn(self.tracker, trail_txn_ids, f"M{len(self.motifs) + 1}", learned_from, name, max_per_day)
        self.motifs[motif.motif_id] = motif
        return motif

