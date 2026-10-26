"""The shapes the review works with: what the bank knows, what Gemini read, and the verdicts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ripple_core.messages import Rail


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# What the bank already knows, from its own records.


class Remitter(Frozen):
    name: str
    ifsc: str | None = None
    account_number: str | None = None


class HeldCredit(Frozen):
    credit_id: str
    rail: Rail
    reference: str
    amount: int  # paise
    at: datetime
    remitter: Remitter
    traced_amount: int


class Kyc(Frozen):
    occupation: str = ""
    business_type: str = ""
    declared_annual_turnover: int | None = None  # paise
    declared_annual_income: int | None = None  # paise


class AccountHolder(Frozen):
    name: str
    gstin: str | None = None
    kyc: Kyc = Kyc()


# What Gemini read from one document. Every field carries the exact words it came from.


class Quoted(Frozen):
    value: str | None = Field(description="The value as printed, or null if the document does not show it")
    quote: str | None = Field(description="The exact words on the page the value was read from, or null")
    page: int | None = Field(default=None, description="1-based page number the quote is on")


class Extraction(Frozen):
    readable: bool = Field(
        description="False if the page cannot be read reliably (blurred, cut off, too dark)"
    )
    document_type: Quoted = Field(description="tax_invoice, e_invoice, bill_of_supply, delivery_challan, "
                                              "salary_slip, rent_agreement, bill, or other")  # fmt: skip
    issuer: Quoted
    issuer_gstin: Quoted
    recipient: Quoted = Field(description="The buyer, employee or licensee the document is addressed to")
    recipient_latin: str | None = Field(description="The recipient's name written in Latin letters, "
                                                    "transliterated if printed in another script")  # fmt: skip
    number: Quoted
    date: Quoted = Field(description="The document date as YYYY-MM-DD in value; the printed date in quote")
    taxable_value: Quoted = Field(
        description="The taxable value before GST in rupees as a plain decimal, if printed"
    )
    total: Quoted = Field(description="The total payable in rupees as a plain decimal, e.g. 59000.00")
    payment_reference: Quoted = Field(description="Any UTR, RRN or payment reference printed on the document")


# The result for each held credit.


class Verdict(StrEnum):
    EXPLAINED = "explained"
    PARTLY_EXPLAINED = "partly_explained"
    NOT_EXPLAINED = "not_explained"
    CONFLICTING = "conflicting"


class Action(StrEnum):
    LIFT = "lift"
    REDUCE = "reduce"
    KEEP = "keep"


class CreditVerdict(Frozen):
    credit_id: str
    verdict: Verdict
    explained_amount: int
    unexplained_amount: int
    document: str | None
    proposed_action: Action
    hold_after: int
    failed_checks: tuple[str, ...]
    reasons: tuple[str, ...]
