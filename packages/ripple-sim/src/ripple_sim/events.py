"""What the simulator sends to each institution's node: `ripple_core.messages` account openings and ledger postings."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from ripple_core.messages import AccountOpening, LedgerPosting, Model, PaiseAmount
from ripple_core.money import fmt_inr


class HolderKind(StrEnum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"


class DeclaredProfile(Model):
    """What the customer declared at account opening (KYC)."""

    holder_kind: HolderKind
    occupation: str
    annual_income: PaiseAmount  # declared income for an individual, turnover for a business
    business_type: str | None = None
    mobile: str | None = None

    def describe(self) -> str:
        """The profile as the one line a node keeps (`AccountOpening.declared_profile`)."""
        income = "turnover" if self.holder_kind is HolderKind.BUSINESS else "income"
        kind = self.business_type or self.holder_kind.value
        return f"{kind}; {self.occupation}; declared annual {income} {fmt_inr(self.annual_income)}"


class Delivery(Model):
    """One message for one member's node, which the simulator signs as the party "sim"."""

    member: str  # the member's id in network.toml
    message: AccountOpening | LedgerPosting

    @property
    def at(self) -> datetime:
        m = self.message
        return m.opened_at if isinstance(m, AccountOpening) else m.payment.at
