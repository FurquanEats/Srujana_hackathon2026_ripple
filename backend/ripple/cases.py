"""Incremental case engine.

Each alert joins the open case of any account it touches whose last alert was within the case window; if it touches
several such cases they merge (union-find). The queue is ordered by tier, then by expected loss = probability x
amount at risk, so a large but merely unusual payment never sits above a Critical ring.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ripple.cash import is_cash_deposit, is_cash_out
from ripple.schema import CaseSummary, ScoredTransaction, Tier


def linked_accounts(txn: ScoredTransaction) -> tuple[str, ...]:
    """Accounts an alert links. A cash deposit's source is the branch counter and a cash-out's destination is an ATM
    or exchange, not a customer, so neither links cases."""
    if is_cash_deposit(txn):
        return (txn.dst_account,)
    if is_cash_out(txn):
        return (txn.src_account,)  # an ATM or exchange account would link every unrelated withdrawal
    return (txn.src_account, txn.dst_account)


@dataclass
class Case:
    case_id: str
    alerts: list[ScoredTransaction] = field(default_factory=list)
    status: str = "open"

    @property
    def accounts(self) -> set[str]:
        return {a for t in self.alerts for a in linked_accounts(t)}

    @property
    def probability(self) -> float:
        return max(t.probability for t in self.alerts)

    def amount_at_risk(self, amount_of: Callable[[str], float]) -> float:
        """The most money any one account in the case moved under alert. Counting each hop would count the same money
        several times as it moves along a chain. For cash structuring, every deposit the reason cites counts, since
        the pattern is the deposits together. `amount_of` returns a transaction's amount by id, or 0 if unknown."""
        moved: dict[str, float] = {}
        for t in self.alerts:
            mover = t.dst_account if is_cash_deposit(t) else t.src_account
            moved[mover] = moved.get(mover, 0.0) + t.amount
            for r in t.reasons:
                if r.code == "cash_structuring":
                    moved[mover] = max(moved[mover], sum(amount_of(i) for i in r.txn_ids))
        return max(moved.values())

    @property
    def typologies(self) -> list[str]:
        return list(dict.fromkeys(r.code for t in self.alerts for r in t.reasons if r.strength >= 0.3))


TIER_ORDER = {Tier.CRITICAL: 0, Tier.REVIEW: 1, Tier.WATCH: 2}


def queue_order(cases: list[CaseSummary]) -> list[CaseSummary]:
    return sorted(cases, key=lambda c: (TIER_ORDER[c.tier], -c.expected_loss))


class CaseEngine:
    def __init__(self, tiers: dict[str, Any], amount_of: Callable[[str], float] = lambda _: 0.0) -> None:
        self.tiers = tiers
        self.amount_of = amount_of
        self.window = timedelta(hours=tiers["case_window_hours"])
        self.cases: dict[str, Case] = {}
        self._parent: dict[str, str] = {}  # union-find over case ids
        self._latest: dict[str, tuple[str, datetime]] = {}  # account -> (case id, time of its last alert)
        self._next = 1

    def _find(self, case_id: str) -> str:
        while self._parent[case_id] != case_id:
            self._parent[case_id] = self._parent[self._parent[case_id]]
            case_id = self._parent[case_id]
        return case_id

    def add(self, alert: ScoredTransaction) -> Case:
        roots = set()
        for account in linked_accounts(alert):
            hit = self._latest.get(account)
            if hit and alert.ts - hit[1] <= self.window:
                root = self._find(hit[0])
                if self.cases[root].status == "open":
                    roots.add(root)
        if roots:
            keep, *others = sorted(roots)  # the oldest case id survives a merge
            case = self.cases[keep]
            for other in others:
                case.alerts.extend(self.cases.pop(other).alerts)
                self._parent[other] = keep
            case.alerts.sort(key=lambda t: t.ts)
        else:
            keep = f"C-{self._next:04d}"
            self._next += 1
            case = self.cases[keep] = Case(case_id=keep)
            self._parent[keep] = keep
        case.alerts.append(alert)
        for account in linked_accounts(alert):
            self._latest[account] = (keep, alert.ts)
        alert.case_id = keep
        for t in case.alerts:
            t.case_id = keep
        return case

    def get(self, case_id: str) -> Case | None:
        root = self._find(case_id) if case_id in self._parent else None
        return self.cases.get(root) if root else None

    def tier(self, case: Case) -> Tier:
        p, t = case.probability, self.tiers
        if p >= t["critical"] or (len(case.accounts) >= t["ring_size_critical"] and p >= t["review"]):
            return Tier.CRITICAL
        if p >= t["review"]:
            return Tier.REVIEW
        return Tier.WATCH

    def summary(self, case: Case) -> CaseSummary:
        p = case.probability
        risk = case.amount_at_risk(self.amount_of)
        return CaseSummary(
            case_id=case.case_id,
            tier=self.tier(case),
            probability=round(p, 4),
            amount_at_risk=round(risk, 2),
            expected_loss=round(p * risk, 2),
            accounts=len(case.accounts),
            transactions=len(case.alerts),
            typologies=case.typologies,
            opened_at=case.alerts[0].ts,
            updated_at=case.alerts[-1].ts,
            status=case.status,
        )

    def ranked(self, status: str | None = "open") -> list[CaseSummary]:
        return queue_order([self.summary(c) for c in self.cases.values() if status is None or c.status == status])
