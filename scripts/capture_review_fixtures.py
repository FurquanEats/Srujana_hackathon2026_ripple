"""Turn the review of the synthetic document set into the grievance officer's evidence packs, and score it.

Uses only extractions Gemini has already made (eval/documents/.review-cache/<model>/), never a new model call, so
it runs without a key or quota. Every case whose documents were all read goes through the real rules
(ripple_review.rules); a case with an unread document is marked unread rather than guessed. Writes:

- web/lib/review/reviews.json: one evidence pack per case, with each document's fields and quotes, and the verdicts;
- web/public/review-docs/<case>/<file>: the documents themselves, so the officer can open them;
- eval/documents/review_results.json: field and verdict accuracy on the cases read, with the coverage stated.

    uv run python scripts/capture_review_fixtures.py --model gemini-3.5-flash
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from ripple_review.docset import load_cases
from ripple_review.evaluate import FIELDS, field_matches
from ripple_review.model import Extraction
from ripple_review.rules import read, review

ROOT = Path(__file__).resolve().parents[1]
DOCSET = ROOT / "eval" / "documents"


def cached(model: str, path: Path) -> Extraction | None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:24]
    file = DOCSET / ".review-cache" / model / f"{digest}.json"
    return Extraction.model_validate_json(file.read_text(encoding="utf-8")) if file.exists() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="gemini-3.5-flash")
    model = parser.parse_args().model
    docs_out = ROOT / "web" / "public" / "review-docs"
    shutil.rmtree(docs_out, ignore_errors=True)
    packs: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    field_hits: dict[str, list[bool]] = {f: [] for f in FIELDS}
    documents_read = documents_total = 0
    for case in load_cases(DOCSET):
        truth = json.loads((case.folder / "truth.json").read_text(encoding="utf-8"))
        extractions: dict[str, Extraction | None] = {}
        documents = []
        for d in case.documents:
            path = case.folder / d["file"]
            (docs_out / case.case_id).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, docs_out / case.case_id / d["file"])
            got = cached(model, path)
            extractions[d["file"]] = got
            documents_total += 1
            documents_read += got is not None
            if got is not None and d["readable"]:
                for f in FIELDS:
                    hit = field_matches(f, got, d["fields"])
                    if hit is not None:
                        field_hits[f].append(hit)
            documents.append({
                "file": d["file"], "url": f"/review-docs/{case.case_id}/{d['file']}", "language": d["language"],
                "form": d["form"], "quality": d["quality"],
                "extraction": got.model_dump(mode="json") if got is not None else None,
            })  # fmt: skip
        complete = all(x is not None for x in extractions.values())
        verdicts = []
        if complete:
            readings = [read(name, x) for name, x in extractions.items() if x is not None]
            for v in review(case.holder, case.credits, readings, case.tds_percent):
                verdicts.append(v.model_dump(mode="json"))
            by_id = {v["credit_id"]: v for v in verdicts}
            for exp in case.expected:
                got_v = by_id[exp["credit_id"]]
                rows.append({
                    "case": case.case_id, "credit": exp["credit_id"], "title": case.title,
                    "expected": exp["verdict"], "got": got_v["verdict"],
                    "correct": got_v["verdict"] == exp["verdict"]
                    and got_v["explained_amount"] == exp["explained_amount"],
                    "unsafe": got_v["verdict"] == "explained" and exp["verdict"] != "explained",
                    "failed_checks": got_v["failed_checks"], "reasons": got_v["reasons"],
                })  # fmt: skip
        packs.append({
            "case_id": case.case_id, "title": case.title, "holder": truth["account_holder"],
            "explanation": truth.get("explanation"), "credits": truth["held_credits"],
            "tds_rate_percent": case.tds_percent, "documents": documents, "read": complete,
            "verdicts": verdicts, "model": model,
        })  # fmt: skip
    review_dir = ROOT / "web" / "lib" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "reviews.json").write_text(json.dumps(packs, ensure_ascii=False, indent=1) + "\n", "utf-8")
    result = {
        "model": model,
        "coverage": {
            "documents_read": documents_read, "documents": documents_total,
            "cases_reviewed": sum(p["read"] for p in packs), "cases": len(packs),
            "note": "Cases with a document the model has not read yet are left out, not guessed.",
        },
        "credits": len(rows),
        "correct": sum(r["correct"] for r in rows),
        "unsafe_explained": sum(r["unsafe"] for r in rows),
        "field_accuracy": {f: round(sum(h) / len(h), 3) if h else None for f, h in field_hits.items()},
        "rows": rows,
    }  # fmt: skip
    out = DOCSET / "review_results.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))
    for r in rows:
        print(f"{'ok ' if r['correct'] else ('UNSAFE' if r['unsafe'] else 'miss'):<6} {r['case']} {r['credit']} "
              f"expected {r['expected']:<17} got {r['got']:<17} {r['title']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
