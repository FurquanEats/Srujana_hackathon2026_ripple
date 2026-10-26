"""Follow victims' money through one account's ledger, the way the MHA SOP's own examples do.

A bank node runs this on its own ledger when a CFCFRMS notice arrives. The rule reproduces both illustrations in
Annexure V of the SOP for NCRP-CFCFRMS (January 2026):

- A debit takes the victims' money before the account holder's own money. In illustration 1 the opening balance of
  Rs 873 is the holder's own and stays with them, while each victim's credit is drawn down by the debit after it.
- When several victims' money is in the account at the moment of a debit, the debit is shared among them pro rata
  to what each has there. In illustration 2 one debit after five victims' credits leaves each victim the same
  share of their loss, which is the SOP's pro-rata release.

Money the account receives that is not traced (its own salary, a shop's takings, or the untraced part of a credit
from an upstream mule) is the holder's own. Payments made after the victims' money has run out are therefore
traced at Rs 0, and the node never liens them.

The trace is a convention, not a legal finding: police and courts decide restoration (SOP para 11).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from ripple_core.money import split_pro_rata

Claim = str  # an NCRP acknowledgement number, one per victim complaint


class LedgerError(ValueError):
    """The ledger does not add up, so no trace can be trusted."""


class Direction(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


@dataclass(frozen=True)
class Entry:
    """One line of the account's statement. `amount` is positive paise."""

    txn_id: str
    at: datetime
    direction: Direction
    amount: int

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise LedgerError(f"{self.txn_id}: amounts must be positive paise")
        if self.at.tzinfo is None:
            raise LedgerError(f"{self.txn_id}: time must be timezone-aware")


@dataclass(frozen=True)
class DebitTrace:
    """A debit and how much of each victim's money it carried out of the account."""

    txn_id: str
    at: datetime
    amount: int
    carried: Mapping[Claim, int]

    @property
    def traced(self) -> int:
        return sum(self.carried.values())


@dataclass(frozen=True)
class AccountTrace:
    remaining: Mapping[Claim, int]  # each victim's money still in the account
    own: int  # the holder's own money still in the account
    debits: tuple[DebitTrace, ...] = field(default=())

    @property
    def balance(self) -> int:
        return self.own + sum(self.remaining.values())

    @property
    def traced_remaining(self) -> int:
        return sum(self.remaining.values())


@dataclass(frozen=True)
class Lien:
    """From `at`, `amount` of a victim's money in the account is set aside, and no later debit can take it."""

    at: datetime
    claim: Claim
    amount: int


def trace_account(
    entries: Iterable[Entry],
    *,
    opening_balance: int,
    traced_in: Mapping[str, Mapping[Claim, int]],
    liens: Iterable[Lien] = (),
    as_of: datetime | None = None,
) -> AccountTrace:
    """Trace victims' money through an account.

    `entries` is the statement from the moment `opening_balance` applies, in ledger order (entries with the same
    time keep their order). `traced_in` names the credits that carry victims' money: credit txn id -> claim -> paise.
    A credit can carry several victims' money, and part of a credit can be untraced. A lien applies to debits
    after its time; entries at the same instant as a lien happened before it.
    """
    rows = sorted(entries, key=lambda e: e.at)  # stable, so same-time entries keep ledger order
    if as_of is not None:
        rows = [e for e in rows if e.at <= as_of]
    if opening_balance < 0:
        raise LedgerError("opening balance cannot be negative")
    _check_traced_in(rows, traced_in)
    pending = sorted(liens, key=lambda lien: lien.at)

    buckets: dict[Claim, int] = {}
    locked: dict[Claim, int] = {}
    own = opening_balance
    debits: list[DebitTrace] = []
    for entry in rows:
        while pending and pending[0].at < entry.at:
            lien = pending.pop(0)
            locked[lien.claim] = min(lien.amount, buckets.get(lien.claim, 0))
        if entry.direction is Direction.CREDIT:
            carried_in = traced_in.get(entry.txn_id, {})
            for claim, paise in carried_in.items():
                buckets[claim] = buckets.get(claim, 0) + paise
            own += entry.amount - sum(carried_in.values())
            continue
        free = {c: b - locked.get(c, 0) for c, b in buckets.items()}
        from_victims = min(entry.amount, sum(free.values()))
        taken = split_pro_rata(from_victims, free) if from_victims else {}
        for claim, paise in taken.items():
            buckets[claim] -= paise
        own -= entry.amount - from_victims
        if own < 0:
            raise LedgerError(f"{entry.txn_id}: the debit is larger than the balance not under a lien")
        debits.append(DebitTrace(entry.txn_id, entry.at, entry.amount, {c: p for c, p in taken.items() if p}))

    return AccountTrace(remaining=buckets, own=own, debits=tuple(debits))


def _check_traced_in(rows: list[Entry], traced_in: Mapping[str, Mapping[Claim, int]]) -> None:
    credit_rows = {e.txn_id: e for e in rows if e.direction is Direction.CREDIT}
    for txn_id, by_claim in traced_in.items():
        credit = credit_rows.get(txn_id)
        if credit is None:
            continue  # a traced credit after `as_of`, or not in this statement
        if any(p <= 0 for p in by_claim.values()):
            raise LedgerError(f"{txn_id}: traced amounts must be positive paise")
        if sum(by_claim.values()) > credit.amount:
            raise LedgerError(f"{txn_id}: more is traced than the credit brought in")
