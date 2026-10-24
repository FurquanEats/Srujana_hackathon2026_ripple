"""Feedback learning: an analyst's verdict on a case changes how Ripple scores from then on.

- Every alert in the case becomes a labelled sample, and the fusion weights take one SGD step on them.
- A confirmed case's accounts feed the graph layer, so their neighbours score higher.
- A dismissed case's account pairs cannot alert again for `dismiss_days`.
- Open cases are rescored with the new weights, and the result says how many changed rank.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ripple.schema import FeedbackResult

if TYPE_CHECKING:
    from ripple.engine import Engine


def apply(engine: Engine, case_id: str, verdict: str) -> FeedbackResult | None:
    case = engine.cases.get(case_id)
    if case is None:
        return None
    before = engine.fusion.snapshot()
    rank_before = [c.case_id for c in engine.cases.ranked()]

    label = 1 if verdict == "confirmed" else 0
    engine.fusion.update([(t.layer_scores, label) for t in case.alerts])
    case.status = verdict
    if verdict == "confirmed":
        engine.graph.mark_confirmed(case.accounts)
    else:
        for t in case.alerts:
            engine.dismissed[(t.src_account, t.dst_account)] = t.ts + engine.dismiss_for

    for open_case in engine.cases.cases.values():
        if open_case.status == "open":
            for t in open_case.alerts:
                t.probability = round(engine.fusion.probability(t.layer_scores), 4)

    rank_after = [c.case_id for c in engine.cases.ranked()]
    still_open = [c for c in rank_before if c in rank_after]
    requeued = sum(1 for i, c in enumerate(still_open) if rank_after.index(c) != i)
    return FeedbackResult(
        case_id=case.case_id,
        status=verdict,
        weights_before={k: round(v, 4) for k, v in before.items()},
        weights_after={k: round(v, 4) for k, v in engine.fusion.snapshot().items()},
        requeued=requeued,
    )
