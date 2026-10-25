"""Load the synthetic document set (eval/documents/cases) in the review's own shapes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ripple_review.model import AccountHolder, HeldCredit, Kyc


@dataclass(frozen=True)
class Case:
    case_id: str
    title: str
    folder: Path
    holder: AccountHolder
    credits: list[HeldCredit]
    tds_percent: float | None
    documents: list[dict[str, Any]]  # the ground truth for each document, including its file name
    expected: list[dict[str, Any]]


def load_cases(root: Path) -> list[Case]:
    cases = []
    for path in sorted((root / "cases").glob("D*/truth.json")):
        truth = json.loads(path.read_text(encoding="utf-8"))
        holder = truth["account_holder"]
        cases.append(
            Case(
                case_id=truth["case_id"],
                title=truth["title"],
                folder=path.parent,
                holder=AccountHolder(
                    name=holder["name"], gstin=holder.get("gstin"), kyc=Kyc(**holder["kyc"])
                ),
                credits=[HeldCredit.model_validate(c) for c in truth["held_credits"]],
                tds_percent=truth.get("tds_rate_percent"),
                documents=truth["documents"],
                expected=truth["expected"],
            )
        )
    return cases
