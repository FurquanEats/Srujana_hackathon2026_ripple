"""The simulated customers and the ledgers they post to.

`World` holds every account's balance so it never posts a debit the account cannot pay, and turns each payment
into the postings each institution would record. It is the only place that builds messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from ripple_core.messages import (
    AccountOpening,
    AccountRef,
    ExitDetail,
    ExitMode,
    LedgerPosting,
    Payment,
    Rail,
)
from ripple_sim.events import DeclaredProfile, Delivery
from ripple_sim.identifiers import SeededIds
from ripple_sim.network import Member

# Limits the simulator respects when choosing a rail, in paise.
UPI_LIMIT = 1_00_000_00
IMPS_LIMIT = 5_00_000_00
RTGS_MINIMUM = 2_00_000_00


class InsufficientFundsError(ValueError):
    pass


@dataclass
class Account:
    member: Member
    number: str
    ifsc: str
    holder: str
    vpa: str | None
    profile: DeclaredProfile
    balance: int
    tags: frozenset[str] = frozenset()

    @property
    def ref(self) -> AccountRef:
        return AccountRef(ifsc=self.ifsc, account_number=self.number)


@dataclass
class World:
    ids: SeededIds
    deliveries: list[Delivery] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    _txn_counters: dict[str, int] = field(default_factory=dict)
    _branches: dict[str, list[str]] = field(default_factory=dict)

    def branch_ifsc(self, member: Member, branch: int) -> str:
        """IFSC of one of a member's branches (each member has a few)."""
        branches = self._branches.setdefault(member.code, [])
        while len(branches) <= branch:
            branches.append(self.ids.ifsc(member.code))
        return branches[branch]

    def open(
        self,
        member: Member,
        holder: str,
        profile: DeclaredProfile,
        opening_balance: int,
        at: datetime,
        *,
        branch: int = 0,
        upi: bool = True,
        tags: frozenset[str] = frozenset(),
    ) -> Account:
        ifsc = self.branch_ifsc(member, branch)
        number = self.ids.account_number()
        vpa = self.ids.vpa(holder, member.upi_handle) if upi else None
        account = Account(member, number, ifsc, holder, vpa, profile, opening_balance, tags)
        self.accounts.append(account)
        self.deliveries.append(
            Delivery(
                member=member.id,
                message=AccountOpening(
                    account_number=number,
                    ifsc=ifsc,
                    holder_name=holder,
                    vpa=vpa,
                    declared_profile=profile.describe(),
                    declared_annual_income=profile.annual_income,
                    opening_balance=opening_balance,
                    opened_at=at.astimezone(UTC),
                ),
            )
        )
        return account

    def _txn_id(self, member: Member) -> str:
        n = self._txn_counters.get(member.code, 0) + 1
        self._txn_counters[member.code] = n
        return f"{member.code}-{n:09d}"

    def choose_rail(self, payer: Account, payee: Account, amount: int, preferred: Rail | None = None) -> Rail:
        if payer.member is payee.member:
            return Rail.INTERNAL
        if preferred is not None:
            return preferred
        if amount <= UPI_LIMIT and payer.vpa and payee.vpa:
            return Rail.UPI
        if amount >= RTGS_MINIMUM:
            return Rail.RTGS
        return Rail.IMPS if amount <= IMPS_LIMIT else Rail.NEFT

    def _reference(self, rail: Rail, payer: Account) -> str:
        if rail in (Rail.UPI, Rail.IMPS):
            return self.ids.rrn()
        if rail is Rail.NEFT:
            return self.ids.neft_utr(payer.member.code)
        if rail is Rail.RTGS:
            return self.ids.rtgs_utr(payer.member.code)
        return self.ids.internal_reference(payer.member.code)

    def pay(
        self, payer: Account, payee: Account, amount: int, at: datetime, rail: Rail | None = None
    ) -> Payment:
        """Move money between two accounts: a debit at the payer's institution and a credit at the payee's."""
        if amount <= 0:
            raise ValueError("amount must be positive paise")
        if amount > payer.balance:
            raise InsufficientFundsError(f"{payer.holder} cannot pay {amount} from {payer.balance}")
        chosen = self.choose_rail(payer, payee, amount, rail)
        payment = Payment(
            rail=chosen, reference=self._reference(chosen, payer), amount=amount, at=at.astimezone(UTC)
        )
        payer.balance -= amount
        payee.balance += amount
        self._post(payer, "debit", payment, counterparty=payee.ref)
        self._post(payee, "credit", payment, counterparty=payer.ref)
        return payment

    def exit(
        self,
        account: Account,
        amount: int,
        at: datetime,
        *,
        mode: ExitMode,
        identifier: str,
        location: str | None = None,
    ) -> Payment:
        """Money leaves the banking system: cash at an ATM, a card payment, a crypto withdrawal."""
        if amount <= 0:
            raise ValueError("amount must be positive paise")
        if amount > account.balance:
            raise InsufficientFundsError(f"{account.holder} cannot take {amount} from {account.balance}")
        payment = Payment(
            rail=Rail.INTERNAL,
            reference=self.ids.rrn(),
            amount=amount,
            at=at.astimezone(UTC),
        )
        account.balance -= amount
        exit_ = ExitDetail(mode=mode, reference=payment.reference, identifier=identifier, location=location)
        self._post(account, "debit", payment, exit_=exit_)
        return payment

    def _post(
        self,
        account: Account,
        direction: Literal["credit", "debit"],
        payment: Payment,
        *,
        counterparty: AccountRef | None = None,
        exit_: ExitDetail | None = None,
    ) -> None:
        self.deliveries.append(
            Delivery(
                member=account.member.id,
                message=LedgerPosting(
                    txn_id=self._txn_id(account.member),
                    account_number=account.number,
                    direction=direction,
                    payment=payment,
                    counterparty=counterparty,
                    exit=exit_,
                ),
            )
        )
