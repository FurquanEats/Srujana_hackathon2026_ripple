"""`ripple-review-eval`: run the review on the synthetic document set and report how it did.

It reports verdict accuracy per held credit, the safety count the PRD sets at zero (credits marked "explained" that
should not be), and how often each field was read exactly as printed. Results go to
eval/documents/review_results.json. Extractions are cached in eval/documents/.review-cache/, which git ignores.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from ripple_review.docset import load_cases
from ripple_review.extract import DEFAULT_MODEL, CachedReader, GeminiReader, Reader
from ripple_review.model import Extraction
from ripple_review.rules import paise, read, review

FIELDS = ("total", "date", "issuer_gstin", "payment_reference")


def api_key(root: Path) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    env_file = root / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("Set GEMINI_API_KEY in .env at the repository root.")
    return key


def field_matches(field: str, extraction: Extraction, truth: dict[str, Any]) -> bool | None:
    expected = truth.get(field)
    got = getattr(extraction, field).value
    if expected is None:
        return got in (None, "")
    if field == "total":
        return bool(paise(got) == expected)
    return (got or "").strip().upper() == str(expected).strip().upper()


def evaluate(root: Path, reader: Reader) -> dict[str, Any]:
    docset = root / "eval" / "documents"
    rows = []
    field_hits: dict[str, list[bool]] = {f: [] for f in FIELDS}
    for case in load_cases(docset):
        extractions = {d["file"]: reader.read(case.folder / d["file"]) for d in case.documents}
        for d in case.documents:
            if d["readable"]:
                for f in FIELDS:
                    hit = field_matches(f, extractions[d["file"]], d["fields"])
                    if hit is not None:
                        field_hits[f].append(hit)
        readings = [read(name, x) for name, x in extractions.items()]
        verdicts = {v.credit_id: v for v in review(case.holder, case.credits, readings, case.tds_percent)}
        for exp in case.expected:
            got = verdicts[exp["credit_id"]]
            rows.append({
                "case": case.case_id,
                "credit": exp["credit_id"],
                "title": case.title,
                "expected": exp["verdict"],
                "got": got.verdict.value,
                "correct": got.verdict.value == exp["verdict"] and got.explained_amount == exp["explained_amount"],
                "unsafe": got.verdict.value == "explained" and exp["verdict"] != "explained",
                "failed_checks": list(got.failed_checks),
                "reasons": list(got.reasons),
            })  # fmt: skip
    return {
        "model": reader.model,
        "credits": len(rows),
        "correct": sum(r["correct"] for r in rows),
        "unsafe_explained": sum(r["unsafe"] for r in rows),
        "field_accuracy": {f: round(sum(h) / len(h), 3) if h else None for f, h in field_hits.items()},
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ripple-review-eval", description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(os.environ.get("RIPPLE_ROOT", Path.cwd()))
    reader = CachedReader(
        GeminiReader(api_key(root), args.model), root / "eval" / "documents" / ".review-cache"
    )
    result = evaluate(root, reader)
    out = root / "eval" / "documents" / "review_results.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for r in result["rows"]:
        mark = "ok " if r["correct"] else ("UNSAFE" if r["unsafe"] else "miss")
        print(
            f"{mark:<6} {r['case']} {r['credit']}  expected {r['expected']:<17} got {r['got']:<17} {r['title']}"
        )
    print(f"\n{result['model']}: {result['correct']} of {result['credits']} credits correct; "
          f"{result['unsafe_explained']} marked explained that should not be.")  # fmt: skip
    print("Fields read exactly as printed: " + ", ".join(f"{k} {v:.0%}" for k, v in
                                                         result["field_accuracy"].items() if v is not None))  # fmt: skip  # noqa: E501
    print(f"Written to {out}")
    return 0 if result["unsafe_explained"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
