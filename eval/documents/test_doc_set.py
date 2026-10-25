# ruff: noqa: S101
"""Checks that the document set's ground truth is consistent with itself and with the rendered files.

uv run --no-project --with pytest --with pypdf --with pillow==13.0.0 --with reportlab==5.1.0 pytest eval/documents
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"

_spec = importlib.util.spec_from_file_location("docset_generate", HERE / "generate.py")
assert _spec
assert _spec.loader
gen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gen  # dataclasses look their module up here
_spec.loader.exec_module(gen)


def load() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASES.glob("D*/truth.json"))]


TRUTHS = load()
BY_ID = {t["case_id"]: t for t in TRUTHS}


def is_gstin(value: str) -> bool:
    return len(value) == 15 and gen.gstin_check_char(value[:14]) == value[14]


def test_every_case_is_listed_and_has_its_files() -> None:
    index = json.loads((CASES / "index.json").read_text(encoding="utf-8"))
    assert [c["case_id"] for c in index] == sorted(BY_ID)
    for t in TRUTHS:
        for d in t["documents"]:
            assert (CASES / t["case_id"] / d["file"]).is_file()


@pytest.mark.parametrize("truth", TRUTHS, ids=lambda t: t["case_id"])
def test_expected_verdicts_are_well_formed(truth: dict[str, Any]) -> None:
    held = {c["credit_id"]: c for c in truth["held_credits"]}
    files = {d["file"] for d in truth["documents"]}
    assert {e["credit_id"] for e in truth["expected"]} == set(held)
    for e in truth["expected"]:
        amount = held[e["credit_id"]]["amount"]
        assert e["verdict"] in gen.VERDICTS
        assert set(e["failed_checks"]) <= set(gen.CHECKS)
        assert e["explained_amount"] + e["unexplained_amount"] == amount
        if e["verdict"] == "explained":
            assert e["explained_amount"] == amount
            assert not e["failed_checks"]
            assert e["document"] in files
            assert e["hold_after"] == 0
        elif e["verdict"] == "partly_explained":
            assert 0 < e["explained_amount"] < amount
            assert e["document"] in files
            assert e["hold_after"] == e["unexplained_amount"]
        else:
            assert e["explained_amount"] == 0
            assert e["failed_checks"]
            assert e["hold_after"] == held[e["credit_id"]]["traced_amount"]


@pytest.mark.parametrize("truth", TRUTHS, ids=lambda t: t["case_id"])
def test_explained_credits_satisfy_every_rule(truth: dict[str, Any]) -> None:
    """For each credit marked explained, re-derive the rules from the truth fields and check they pass."""
    held = {c["credit_id"]: c for c in truth["held_credits"]}
    docs = {d["file"]: d for d in truth["documents"]}
    for e in truth["expected"]:
        if e["verdict"] != "explained":
            continue
        credit, doc = held[e["credit_id"]], docs[e["document"]]
        f = doc["fields"]
        assert doc["readable"]
        assert doc["planted_instruction"] is None
        expected_amount = f["total"]
        if truth["tds_rate_percent"]:
            tds = gen.pct(f["taxable_value"], Decimal(truth["tds_rate_percent"]))
            expected_amount -= tds
        assert credit["amount"] == expected_amount
        paid_on = datetime.fromisoformat(credit["at"]).date()
        assert datetime.fromisoformat(f["date"]).date() <= paid_on + timedelta(days=7)
        if f["issuer_gstin"]:
            assert is_gstin(f["issuer_gstin"])


def test_each_hard_case_fails_for_its_stated_reason() -> None:
    d04 = BY_ID["D04"]
    assert d04["held_credits"][0]["amount"] == 2 * d04["documents"][0]["fields"]["total"]

    for cid, days in (("D05", 45), ("D11", 19)):
        t = BY_ID[cid]
        paid = datetime.fromisoformat(t["held_credits"][0]["at"]).date()
        assert datetime.fromisoformat(t["documents"][0]["fields"]["date"]).date() == paid + timedelta(
            days=days
        )

    d06 = BY_ID["D06"]
    assert d06["documents"][0]["fields"]["payment_reference"] == d06["held_credits"][0]["reference"]
    assert d06["held_credits"][0]["amount"] == d06["held_credits"][1]["amount"]

    d07 = BY_ID["D07"]
    assert not is_gstin(d07["documents"][0]["fields"]["issuer_gstin"])
    assert is_gstin(d07["account_holder"]["gstin"])

    assert not BY_ID["D08"]["documents"][0]["readable"]

    for cid in ("D12", "D13"):
        t = BY_ID[cid]
        assert t["documents"][0]["fields"]["recipient"].upper() != t["held_credits"][0]["remitter"]["name"]

    d16 = BY_ID["D16"]
    assert (
        d16["documents"][0]["fields"]["total"] > 2 * d16["account_holder"]["kyc"]["declared_annual_turnover"]
    )


def test_all_gstins_are_valid_except_the_planted_one() -> None:
    bad = []
    for t in TRUTHS:
        for d in t["documents"]:
            for key in ("issuer_gstin", "recipient_gstin"):
                g = d["fields"][key]
                if g and not is_gstin(g):
                    bad.append((t["case_id"], key))
    assert bad == [("D07", "issuer_gstin")]


def test_payment_references_have_the_right_format() -> None:
    patterns = {
        "upi": r"^\d{12}$",
        "imps": r"^\d{12}$",
        "neft": r"^[A-Z]{4}N\d{11}$",
        "rtgs": r"^[A-Z]{4}R\d{17}$",
    }
    for t in TRUTHS:
        for c in t["held_credits"]:
            assert re.match(patterns[c["rail"]], c["reference"]), (t["case_id"], c["reference"])
            assert re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", c["remitter"]["ifsc"])


def test_text_pdfs_carry_the_figures_and_the_planted_text() -> None:
    d01 = BY_ID["D01"]
    text = PdfReader(CASES / "D01" / d01["documents"][0]["file"]).pages[0].extract_text()
    assert gen.inr(d01["documents"][0]["fields"]["total"]) in text

    d12 = BY_ID["D12"]
    text = PdfReader(CASES / "D12" / d12["documents"][0]["file"]).pages[0].extract_text()
    assert "ignore previous instructions" in text  # present in the text layer, invisible on the page


def digest(folder: Path, pattern: str) -> dict[Path, bytes]:
    files = (p for p in sorted(folder.rglob(pattern)) if p.is_file())
    return {p.relative_to(folder): hashlib.sha256(p.read_bytes()).digest() for p in files}


def test_generator_reproduces_the_ground_truth(tmp_path: Path) -> None:
    """The committed truth files are what the generator makes now, and two runs give identical files.

    Rendered PDFs and images are compared run against run, not against the committed ones, because their bytes
    depend on the Pillow and reportlab versions (generate.py pins the ones that made the committed files).
    """
    gen.main(tmp_path / "a")
    gen.main(tmp_path / "b")
    assert digest(tmp_path / "a", "*.json") == digest(CASES, "*.json")
    assert digest(tmp_path / "a", "*") == digest(tmp_path / "b", "*")
