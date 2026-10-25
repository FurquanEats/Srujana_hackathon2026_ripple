"""The messages bank nodes and the hubs exchange.

They carry only what the MHA SOP for NCRP-CFCFRMS already requires banks to report: the amount held, the onward
transfers and the exit details (SOP paras 6.1 and 9.1). Every model is frozen and rejects unknown fields, and every
amount is whole paise. Each message travels inside a signed envelope (see `ripple_core.signing`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ripple_core import ids

PaiseAmount = Annotated[int, Field(ge=0)]
PositivePaise = Annotated[int, Field(gt=0)]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class Rail(StrEnum):
    UPI = "upi"
    IMPS = "imps"
    NEFT = "neft"
    RTGS = "rtgs"
    INTERNAL = "internal"  # a transfer between two accounts at the same bank


class ExitMode(StrEnum):
    """Ways money leaves the banking system, each with the identifier SOP para 9.1 asks for."""

    ATM = "atm"  # ATM ID
    AEPS = "aeps"  # device ID or business correspondent agent
    POS = "pos"  # merchant and acquirer
    CHEQUE = "cheque"  # cheque number and branch
    CRYPTO = "crypto"  # exchange and wallet
    LOAN_REPAYMENT = "loan_repayment"  # loan account
    CARD_REPAYMENT = "card_repayment"  # card account


class AccountType(StrEnum):
    """Nodal, pool and escrow accounts get a hold on the disputed amount only (SOP 9.1 iii)."""

    REGULAR = "regular"
    NODAL = "nodal"
    POOL = "pool"
    ESCROW = "escrow"


class LegalBasis(StrEnum):
    HOLD_NOTICE = "BNSS s.168 read with s.94"
    SEIZURE = "BNSS s.106"


class AccountRef(Model):
    """An account at an institution: an account number with its IFSC, or a UPI ID."""

    ifsc: str | None = None
    account_number: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")] | None = None
    vpa: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.ifsc is not None and not ids.is_ifsc(self.ifsc):
            raise ValueError(f"not an IFSC: {self.ifsc!r}")
        if self.vpa is not None and not ids.is_vpa(self.vpa):
            raise ValueError(f"not a UPI ID: {self.vpa!r}")
        if (self.account_number is None) != (self.ifsc is None):
            raise ValueError("an account number needs its IFSC, and an IFSC needs an account number")
        if self.account_number is None and self.vpa is None:
            raise ValueError("give an account number with IFSC, or a UPI ID")
        return self


class Payment(Model):
    """One payment as both banks record it."""

    rail: Rail
    reference: str
    amount: PositivePaise
    at: AwareDatetime

    @model_validator(mode="after")
    def _check_reference(self) -> Self:
        valid = {
            Rail.UPI: ids.is_rrn,
            Rail.IMPS: ids.is_rrn,
            Rail.NEFT: ids.is_neft_utr,
            Rail.RTGS: ids.is_rtgs_utr,
        }.get(self.rail)
        if valid is not None and not valid(self.reference):
            raise ValueError(f"{self.reference!r} is not a valid {self.rail.value.upper()} reference")
        if not self.reference:
            raise ValueError("a payment needs a reference")
        return self


class Notice(Model):
    """CFCFRMS asks a bank to hold the victim's money in a credit and report where it went (SOP 6.1 g)."""

    notice_id: Annotated[str, Field(min_length=8, max_length=64)]
    ack_number: str
    legal_basis: LegalBasis = LegalBasis.HOLD_NOTICE
    layer: Annotated[int, Field(ge=1)]
    credit: Payment
    beneficiary: AccountRef
    traced_amount: PositivePaise  # how much of this credit is the victim's money
    issued_at: AwareDatetime

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not ids.is_ncrp_ack(self.ack_number):
            raise ValueError(f"not an NCRP acknowledgement number: {self.ack_number!r}")
        if self.traced_amount > self.credit.amount:
            raise ValueError("traced amount cannot exceed the credit")
        return self


class OnwardHop(Model):
    """A later debit that carried some of the victim's money to another account."""

    payment: Payment
    to: AccountRef
    traced_amount: PositivePaise

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.traced_amount > self.payment.amount:
            raise ValueError("traced amount cannot exceed the payment")
        return self


class Exit(Model):
    """Money that left the banking system, with the identifier police need (SOP 9.1 i)."""

    mode: ExitMode
    reference: Annotated[str, Field(min_length=1)]
    at: AwareDatetime
    amount: PositivePaise
    traced_amount: PositivePaise
    identifier: Annotated[str, Field(min_length=1)]  # ATM ID, device ID, wallet, merchant or loan account
    location: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.traced_amount > self.amount:
            raise ValueError("traced amount cannot exceed the exit amount")
        return self


class NoticeResponse(Model):
    """The bank's answer. Held + passed on + cashed out must equal the traced amount that arrived."""

    notice_id: str
    status: Literal["matched", "not_found"]
    reason: str | None = None
    traced_in: PaiseAmount = 0
    account_type: AccountType | None = None
    holder_name: str | None = None  # KYC the bank must report (SOP 6.1 k)
    held_amount: PaiseAmount = 0
    lien_id: str | None = None
    onward: tuple[OnwardHop, ...] = ()
    exits: tuple[Exit, ...] = ()
    responded_at: AwareDatetime

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.status == "not_found":
            if not self.reason:
                raise ValueError("a not-found response must say why")
            if self.held_amount or self.onward or self.exits or self.traced_in:
                raise ValueError("a not-found response cannot hold or trace money")
            return self
        if self.account_type is None:
            raise ValueError("a matched response must give the account type")
        if (self.held_amount > 0) != (self.lien_id is not None):
            raise ValueError("a held amount needs a lien ID, and a lien ID needs a held amount")
        accounted = (
            self.held_amount
            + sum(h.traced_amount for h in self.onward)
            + sum(e.traced_amount for e in self.exits)
        )
        if accounted != self.traced_in:
            raise ValueError(
                f"held + passed on + cashed out ({accounted}) must equal the traced amount in ({self.traced_in})"
            )
        return self


class ExitDetail(Model):
    """Where a debit left the banking system, as the bank's own records show it."""

    mode: ExitMode
    reference: Annotated[str, Field(min_length=1)]
    identifier: Annotated[str, Field(min_length=1)]
    location: str | None = None


class AccountOpening(Model):
    """An account the bank holds. In the simulation the node's ledger stands in for core banking."""

    account_number: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")]
    ifsc: str
    holder_name: Annotated[str, Field(min_length=1, max_length=120)]
    account_type: AccountType = AccountType.REGULAR
    vpa: str | None = None
    declared_profile: Annotated[str, Field(max_length=200)] = ""
    opening_balance: PaiseAmount = 0
    opened_at: AwareDatetime

    @model_validator(mode="after")
    def _check(self) -> Self:
        AccountRef(ifsc=self.ifsc, account_number=self.account_number, vpa=self.vpa)
        return self


class LedgerPosting(Model):
    """One line posted to an account: a transfer in or out, or money leaving the system through an exit."""

    txn_id: Annotated[str, Field(min_length=1, max_length=64)]
    account_number: Annotated[str, Field(pattern=r"^[0-9A-Z]{6,20}$")]
    direction: Literal["credit", "debit"]
    payment: Payment
    counterparty: AccountRef | None = None
    exit: ExitDetail | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.direction == "credit" and (self.counterparty is None or self.exit is not None):
            raise ValueError("a credit names the account it came from and has no exit")
        if self.direction == "debit" and (self.counterparty is None) == (self.exit is None):
            raise ValueError("a debit goes either to another account or out through an exit")
        return self


class Complaint(Model):
    """A complaint pushed to CFCFRMS by a police officer (SOP 6.1 f), naming the victim's payment."""

    ack_number: str
    victim_name: Annotated[str, Field(min_length=1, max_length=120)]
    payment: Payment
    beneficiary: AccountRef
    filed_at: AwareDatetime

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not ids.is_ncrp_ack(self.ack_number):
            raise ValueError(f"not an NCRP acknowledgement number: {self.ack_number!r}")
        return self


class RiskLevel(StrEnum):
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class RiskSignal(Model):
    """A bank tells DPIP that an account looks like a mule, without revealing the account (PRD: Security)."""

    identifier_hashes: Annotated[
        tuple[Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")], ...], Field(min_length=1)
    ]
    level: RiskLevel
    reason_code: Annotated[str, Field(pattern=r"^[a-z_]{3,40}$")]
    expires_at: AwareDatetime
