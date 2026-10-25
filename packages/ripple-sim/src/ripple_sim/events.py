"""What the simulator sends to each institution's node.

TODO(rebuild/node-hub): `AccountOpening`, `LedgerPosting` and `ExitDetail` stand in for the messages that pull
request adds to `ripple_core.messages`, with the fields it describes. Once it lands, import them from there and
delete these copies; the simulator only builds them in `world.py`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, Field

from ripple_core.messages import AccountRef, AccountType, ExitMode, Model, Payment
from ripple_core.tracing import Direction

Paise = Annotated[int, Field(ge=0)]


class HolderKind(StrEnum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"


class DeclaredProfile(Model):
    """What the customer declared at account opening (KYC)."""

    holder_kind: HolderKind
    occupation: str
    annual_income: Paise  # declared income for an individual, turnover for a business
    business_type: str | None = None
    mobile: str | None = None


class AccountOpening(Model):
    account_number: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")]
    ifsc: str
    holder: str
    account_type: AccountType
    vpa: str | None
    profile: DeclaredProfile
    opening_balance: Paise
    opened_at: AwareDatetime


class ExitDetail(Model):
    """Where money left the banking system, with the identifier the SOP asks for (para 9.1)."""

    mode: ExitMode
    identifier: Annotated[str, Field(min_length=1)]  # ATM ID, merchant ID, wallet address
    location: str | None = None


class LedgerPosting(Model):
    txn_id: Annotated[str, Field(min_length=1)]
    account_number: str
    direction: Direction
    payment: Payment
    counterparty: AccountRef | ExitDetail


class Delivery(Model):
    """One message for one member's node, which the simulator signs as the party "sim"."""

    member: str
    message: AccountOpening | LedgerPosting

    @property
    def at(self) -> datetime:
        m = self.message
        return m.opened_at if isinstance(m, AccountOpening) else m.payment.at
