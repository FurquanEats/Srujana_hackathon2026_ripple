"""The rules that decide each held credit's verdict from what Gemini read. No model takes part here.

Checks, as the document set defines them (eval/documents/README.md):

- readable: the document can be read; an unreadable one never supports a credit.
- quote_support: every field used (total, date, payer) has the words it was read from.
- amount_match: the total equals the credit, exactly or net of the TDS rate on the taxable value.
- date_order: the document is dated before the payment, or at most 7 days after it.
- payer_match: the payer on the document is the remitter in the bank's own payment record.
- gstin_valid: the issuer's GSTIN has the right check character and, if the bank holds one, matches the KYC GSTIN.
- document_reuse: no document explains two credits.
- business_fit: the credit is not larger than the holder's whole declared annual turnover or income.

A payer mismatch, a reused document or a business misfit makes the credit "conflicting". An unreadable document,
missing quotes, a bad GSTIN or a date after the payment make it "not explained". A smaller total makes it "partly
explained". Only a credit that passes every check is "explained".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from ripple_core import ids
from ripple_review.model import (
    AccountHolder,
    Action,
    CreditVerdict,
    Extraction,
    HeldCredit,
    Verdict,
)

DATE_GRACE = timedelta(days=7)
AMOUNT_TOLERANCE = 100  # paise: one rupee of rounding
PAYER_IS_ISSUER = frozenset({"salary_slip"})  # the employer issues the slip and pays the salary
GSTIN_DOCUMENTS = frozenset({"tax_invoice", "e_invoice", "bill_of_supply", "bill"})  # CGST Rules 46 and 49
STOPWORDS = frozenset(
    {"pvt", "private", "ltd", "limited", "llp", "the", "ms", "m", "s", "and", "co", "company", "shri", "shree",
     "sri", "smt", "mr", "mrs"}
)  # fmt: skip


@dataclass(frozen=True)
class Reading:
    """One document as the rules use it: values parsed, with a note of anything missing."""

    name: str
    extraction: Extraction
    total: int | None
    taxable: int | None
    on: date | None
    payer: str | None

    @property
    def kind(self) -> str:
        return (self.extraction.document_type.value or "other").strip().lower()

    @property
    def quoted(self) -> bool:
        x = self.extraction
        payer_field = x.issuer if self.kind in PAYER_IS_ISSUER else x.recipient
        return all(f.value and f.quote for f in (x.total, x.date, payer_field))


def paise(text: str | None) -> int | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return int((value * 100).to_integral_value())


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None


def read(name: str, extraction: Extraction) -> Reading:
    kind = (extraction.document_type.value or "").strip().lower()
    payer = (
        extraction.issuer.value
        if kind in PAYER_IS_ISSUER
        else (extraction.recipient_latin or extraction.recipient.value)
    )
    return Reading(
        name,
        extraction,
        paise(extraction.total.value),
        paise(extraction.taxable_value.value),
        parse_date(extraction.date.value),
        payer,
    )


def _skeleton(token: str) -> str:
    """A rough sound-key for Indian names written in Latin letters: Meenakshi and Minakshi both give 'mnksh'."""
    t = token.replace("ph", "f").replace("x", "ks").replace("c", "k").replace("q", "k").replace("z", "j")
    return re.sub(r"[aeiouyh]", "", t)


def _tokens(name: str) -> list[str]:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return [t for t in re.findall(r"[a-z0-9]+", ascii_name) if t not in STOPWORDS]


def same_party(a: str | None, b: str | None) -> bool:
    """Whether two names plausibly name the same party: every significant word of the shorter name appears in the
    longer, allowing for transliteration ('Rathaur Caterers' and 'RATHORE CATERERS')."""
    if not a or not b:
        return False
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return all(any(s == t or (len(s) >= 3 and _skeleton(s) == _skeleton(t)) for t in long_) for s in short)


def _amount_matches(reading: Reading, amount: int, tds_percent: float | None) -> bool:
    if reading.total is None:
        return False
    if abs(reading.total - amount) <= AMOUNT_TOLERANCE:
        return True
    if tds_percent:
        base = reading.taxable if reading.taxable is not None else reading.total
        net = reading.total - round(base * Decimal(str(tds_percent)) / 100)
        return abs(net - amount) <= AMOUNT_TOLERANCE
    return False


def review(
    holder: AccountHolder,
    credits: list[HeldCredit],  # noqa: A002 - the bank calls them credits
    readings: list[Reading],
    tds_percent: float | None = None,
) -> list[CreditVerdict]:
    """Decide every held credit. A document that prints a credit's payment reference belongs to that credit first;
    otherwise each credit takes the unused document whose total matches it, then one whose payer matches it."""
    assigned: dict[str, str] = {}  # document name -> credit id
    for r in readings:
        ref = r.extraction.payment_reference.value
        for c in credits:
            if ref and ref.strip() == c.reference:
                assigned[r.name] = c.credit_id
    verdicts = []
    for credit in credits:
        doc = next((r for r in readings if assigned.get(r.name) == credit.credit_id), None)
        reused = False
        if doc is None:
            fitting = [r for r in readings if _amount_matches(r, credit.amount, tds_percent)
                       or same_party(r.payer, credit.remitter.name)]  # fmt: skip
            free = [r for r in fitting if r.name not in assigned]
            amount_first = sorted(free, key=lambda r: not _amount_matches(r, credit.amount, tds_percent))
            doc = amount_first[0] if amount_first else None
            reused = doc is None and bool(fitting)
            if doc is not None:
                assigned[doc.name] = credit.credit_id
        verdicts.append(_decide(holder, credit, doc, reused, tds_percent))
    return verdicts


def _decide(  # noqa: PLR0911, PLR0912 - one return per verdict path
    holder: AccountHolder, credit: HeldCredit, doc: Reading | None, reused: bool, tds_percent: float | None
) -> CreditVerdict:
    if reused:
        return _verdict(credit, Verdict.CONFLICTING, 0, None, ["document_reuse"],
                        ["The only document offered already explains another held credit."])  # fmt: skip
    if doc is None:
        return _verdict(credit, Verdict.NOT_EXPLAINED, 0, None, ["quote_support"],
                        ["No document was offered for this credit."])  # fmt: skip
    if not doc.extraction.readable:
        return _verdict(credit, Verdict.NOT_EXPLAINED, 0, doc.name, ["readable", "quote_support"],
                        [f"{doc.name} cannot be read reliably, so it cannot support the credit."])  # fmt: skip

    failed: list[str] = []
    reasons: list[str] = []
    if not doc.quoted:
        failed.append("quote_support")
        reasons.append("The total, date or payer was not read from the page with its exact words.")
    gstin = doc.extraction.issuer_gstin.value
    if doc.kind in GSTIN_DOCUMENTS and gstin:
        gstin = gstin.strip().upper()
        if not ids.is_gstin(gstin) or (holder.gstin and gstin != holder.gstin.upper()):
            failed.append("gstin_valid")
            reasons.append(
                f"The issuer GSTIN {gstin} fails its check character or differs from the bank's KYC."
            )
    if doc.on is not None and doc.on > credit.at.date() + DATE_GRACE:
        failed.append("date_order")
        reasons.append(f"The document is dated {doc.on.isoformat()}, more than 7 days after the payment.")
    payer_ok = same_party(doc.payer, credit.remitter.name)
    if not payer_ok:
        failed.append("payer_match")
        reasons.append(f"The document names {doc.payer or 'no payer'}, but {credit.remitter.name} paid.")
    declared = holder.kyc.declared_annual_turnover or holder.kyc.declared_annual_income
    if declared and credit.amount > declared:
        failed.append("business_fit")
        reasons.append("The credit is larger than the holder's whole declared annual turnover or income.")

    if {"payer_match", "business_fit"} & set(failed):
        return _verdict(credit, Verdict.CONFLICTING, 0, doc.name, failed, reasons)
    if failed:
        return _verdict(credit, Verdict.NOT_EXPLAINED, 0, doc.name, failed, reasons)
    if _amount_matches(doc, credit.amount, tds_percent):
        return _verdict(credit, Verdict.EXPLAINED, credit.amount, doc.name, [],
                        [f"{doc.name} accounts for the whole credit and every check passes."])  # fmt: skip
    if doc.total is not None and 0 < doc.total < credit.amount:
        return _verdict(credit, Verdict.PARTLY_EXPLAINED, doc.total, doc.name, ["amount_match"],
                        [f"{doc.name} accounts for part of the credit; the rest is unexplained."])  # fmt: skip
    return _verdict(credit, Verdict.NOT_EXPLAINED, 0, doc.name, ["amount_match"],
                    [f"The document's total does not match the credit of {credit.amount} paise."])  # fmt: skip


def _verdict(  # noqa: PLR0917
    credit: HeldCredit,
    verdict: Verdict,
    explained: int,
    document: str | None,
    failed: list[str],
    reasons: list[str],
) -> CreditVerdict:
    unexplained = credit.amount - explained
    action = {Verdict.EXPLAINED: Action.LIFT, Verdict.PARTLY_EXPLAINED: Action.REDUCE}.get(
        verdict, Action.KEEP
    )
    hold_after = 0 if verdict is Verdict.EXPLAINED else min(credit.traced_amount, unexplained)
    return CreditVerdict(
        credit_id=credit.credit_id,
        verdict=verdict,
        explained_amount=explained,
        unexplained_amount=unexplained,
        document=document,
        proposed_action=action,
        hold_after=hold_after,
        failed_checks=tuple(failed),
        reasons=tuple(reasons),
    )
