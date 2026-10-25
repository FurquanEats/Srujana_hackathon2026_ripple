"""Loads the sample responses in /fixtures, validated against the schema. Regenerate them with scripts/make_fixtures.py."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ripple.schema import CaseDetail, CaseSummary, EvalReport

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def cases() -> list[CaseSummary]:
    return [CaseSummary.model_validate(c) for c in _load("cases.json")]


@lru_cache(maxsize=None)
def case_detail(case_id: str) -> CaseDetail | None:
    # Only known ids reach the file system and the cache: an id from the URL could otherwise name another .json file
    # (a backslash is a path separator on Windows) or grow the unbounded cache one miss at a time.
    if case_id not in {c.case_id for c in cases()}:
        return None
    path = FIXTURES_DIR / f"case_{case_id}.json"
    if not path.is_file():
        return None
    return CaseDetail.model_validate(_load(path.name))


@lru_cache(maxsize=None)
def eval_report() -> EvalReport:
    return EvalReport.model_validate(_load("eval.json"))


def stream_events() -> list[dict[str, Any]]:
    return _load("stream_sample.json")
