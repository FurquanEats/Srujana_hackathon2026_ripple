"""The rules alone, fed with perfect readings of every document: they must reach every expected verdict.

This separates the rules from Gemini: any miss here is a rules bug, not a reading error.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from ripple_review.docset import Case, load_cases
from ripple_review.model import Extraction, Quoted
from ripple_review.rules import document_kind, parse_date, read, review, same_party

DOCSET = Path(__file__).resolve().parents[3] / "eval" / "documents"
CASES = load_cases(DOCSET)
# What a reader would write in Latin letters for names printed in Devanagari.
TRANSLITERATIONS = {"मीनाक्षी टेक्सटाइल्स": "Meenakshi Textiles", "राठौर कैटरर्स": "Rathaur Caterers"}


def rupees_text(paise: int | None) -> str | None:
    return None if paise is None else f"{paise / 100:.2f}"


def perfect(doc: dict[str, Any]) -> Extraction:
    f = doc["fields"]

    def q(value: Any) -> Quoted:
        return Quoted(
            value=None if value is None else str(value), quote=None if value is None else str(value)
        )

    readable = bool(doc["readable"])
    blank = Quoted(value=None, quote=None)
    return Extraction(
        readable=readable,
        document_type=q(f["document_type"]),
        issuer=q(f["issuer"]),
        issuer_gstin=q(f["issuer_gstin"]),
        recipient=q(f["recipient"]),
        recipient_latin=TRANSLITERATIONS.get(f["recipient"] or "", f["recipient"]),
        number=q(f["number"]),
        date=q(f["date"]) if readable else blank,
        taxable_value=q(rupees_text(f["taxable_value"])),
        total=q(rupees_text(f["total"])) if readable else blank,
        payment_reference=q(f["payment_reference"]),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_rules_reach_every_expected_verdict_from_perfect_readings(case: Case) -> None:
    readings = [read(d["file"], perfect(d)) for d in case.documents]
    verdicts = {v.credit_id: v for v in review(case.holder, case.credits, readings, case.tds_percent)}
    for expected in case.expected:
        got = verdicts[expected["credit_id"]]
        assert got.verdict.value == expected["verdict"], got.reasons
        assert got.explained_amount == expected["explained_amount"]
        assert got.hold_after == expected["hold_after"]
        assert set(got.failed_checks) >= set(expected["failed_checks"])


def test_every_case_was_loaded() -> None:
    assert len(CASES) == 17
    assert sum(len(c.credits) for c in CASES) == 19


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Navkar Logistics Pvt Ltd", "NAVKAR LOGISTICS PVT LTD", True),
        ("Minakshi Textiles", "MEENAKSHI TEXTILES", True),
        ("Rathaur Caterers", "RATHORE CATERERS", True),
        ("Verma Motors", "KUNAL SINGH", False),
        ("Galaxy Telecom", "Galaxy Mobiles", False),
        (None, "Anyone", False),
        ("Pvt Ltd", "Some Company", False),
    ],
)
def test_payer_names_match_across_spellings_but_not_across_parties(a: str | None, b: str, same: bool) -> None:
    assert same_party(a, b) is same


def test_a_bill_of_supply_with_another_gstin_fails_the_gstin_check() -> None:
    case = next(c for c in CASES if c.case_id == "D17")
    doc = next(d for d in case.documents if d["fields"]["document_type"] == "bill_of_supply")
    other = Quoted(value="27AAAAA0000A1Z5", quote="27AAAAA0000A1Z5")
    forged = perfect(doc).model_copy(update={"issuer_gstin": other})
    verdicts = {v.credit_id: v for v in review(case.holder, case.credits, [read(doc["file"], forged)])}
    assert "gstin_valid" in verdicts["C1"].failed_checks


def as_the_model_writes_it(doc: dict[str, Any]) -> Extraction:
    """A perfect reading, spelled the way Gemini actually returns it: 'Tax Invoice' and a day-first date."""
    reading = perfect(doc)
    kind = (reading.document_type.value or "").replace("_", " ").title()
    day_first = reading.date.value
    if day_first:
        day_first = date.fromisoformat(day_first).strftime("%d/%m/%Y")
    return reading.model_copy(update={
        "document_type": Quoted(value=kind, quote=kind),
        "date": Quoted(value=day_first, quote=day_first) if day_first else reading.date,
    })  # fmt: skip


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.case_id)
def test_the_model_s_spelling_of_dates_and_types_changes_no_verdict(case: Case) -> None:
    readings = [read(d["file"], as_the_model_writes_it(d)) for d in case.documents]
    verdicts = {v.credit_id: v for v in review(case.holder, case.credits, readings, case.tds_percent)}
    for exp in case.expected:
        assert verdicts[exp["credit_id"]].verdict.value == exp["verdict"], case.case_id


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2026-11-17", date(2026, 11, 17)), ("17/11/2026", date(2026, 11, 17)), ("17-11-26", date(2026, 11, 17)),
     ("17.11.2026", date(2026, 11, 17)), ("17 Nov 2026", date(2026, 11, 17)), ("17 November, 2026", date(2026, 11, 17)),
     ("31/02/2026", None), ("next Tuesday", None), (None, None)],
)  # fmt: skip
def test_indian_day_first_dates_are_read(text: str | None, expected: date | None) -> None:
    assert parse_date(text) == expected


def test_a_date_that_cannot_be_read_never_explains_a_credit() -> None:
    case = next(c for c in CASES if c.case_id == "D01")
    doc = case.documents[0]
    vague = perfect(doc).model_copy(update={"date": Quoted(value="mid October", quote="mid October")})
    [verdict] = review(case.holder, case.credits, [read(doc["file"], vague)])
    assert verdict.verdict.value == "not_explained"
    assert "date_order" in verdict.failed_checks


def test_document_kinds_are_normalised() -> None:
    assert document_kind("Tax Invoice") == document_kind("tax-invoice") == "tax_invoice"
    assert document_kind("E-Invoice") == "e_invoice"
    assert document_kind(None) == "other"
