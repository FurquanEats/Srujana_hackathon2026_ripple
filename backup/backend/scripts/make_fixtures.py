"""Writes the sample API responses in /fixtures. Run from backend/: python scripts/make_fixtures.py

The numbers are illustrative sample data, not measured results. Measured metrics come from ripple.eval.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ripple.schema import (  # noqa: E402
    AccountProfile,
    BudgetPoint,
    CaseDetail,
    CaseSummary,
    EvalReport,
    GraphEdge,
    GraphNode,
    Layer,
    MetricRow,
    Rail,
    Reason,
    ScoredTransaction,
    ShapValue,
    StreamEvent,
    Tier,
)

OUT = Path(__file__).resolve().parents[2] / "fixtures"
T0 = datetime(2026, 10, 24, 14, 0, 0)


def txn(n, minutes, src, dst, amount, rail=Rail.UPI, prob=0.1, reasons=(), device="D10", case_id=None):
    return ScoredTransaction(
        txn_id=f"T{n:06d}",
        ts=T0 + timedelta(minutes=minutes),
        src_account=src,
        dst_account=dst,
        amount=amount,
        rail=rail,
        src_handle=f"{src.lower()}@okbank" if rail == Rail.UPI else None,
        device_id=device,
        location="Bengaluru",
        channel="mobile" if rail != Rail.CASH else "branch",
        probability=prob,
        confidence=1.0 if device else 0.7,
        layer_scores={Layer.DETECTOR: prob, Layer.BASELINE: prob * 0.6, Layer.GRAPH: prob * 0.8, Layer.MODEL: prob},
        reasons=list(reasons),
        is_alert=prob >= 0.6,
        case_id=case_id,
    )


def mule_ring() -> CaseDetail:
    victims = [f"A10{i:02d}" for i in range(1, 8)]
    amounts = [9_500, 12_000, 4_999, 15_000, 7_800, 11_200, 8_300]
    timeline = [
        txn(100 + i, i * 18, v, "A2217", a, prob=0.55, case_id="C-0001") for i, (v, a) in enumerate(zip(victims, amounts))
    ]
    total_in = sum(amounts)
    fan_in = Reason(
        layer=Layer.DETECTOR,
        code="fan_in_out",
        text=f"7 accounts paid A2217 within 2 hours (Rs {total_in:,}), then A2217 moved 90% of it out",
        strength=0.93,
        txn_ids=[t.txn_id for t in timeline] + ["T000110", "T000111"],
        counterfactual="Not flagged if fewer than 5 distinct senders had paid A2217 within 24 hours",
    )
    pass_through = Reason(
        layer=Layer.DETECTOR,
        code="pass_through",
        text="A2217 forwarded Rs 36,000 to A5120 six minutes after the last incoming payment (T000106 -> T000110)",
        strength=0.88,
        txn_ids=["T000106", "T000110"],
        counterfactual="Not flagged if the onward transfer had come more than 30 minutes later",
    )
    graph = Reason(
        layer=Layer.GRAPH,
        code="community",
        text="A2217, A5120, A5121 and A9001 form a dense community; A9001 has the highest PageRank in it",
        strength=0.81,
        txn_ids=["T000110", "T000111", "T000112", "T000113"],
    )
    baseline = Reason(
        layer=Layer.BASELINE,
        code="baseline_velocity",
        text="A2217 usually receives 1 payment a day; it received 7 in 2 hours",
        strength=0.74,
        txn_ids=[t.txn_id for t in timeline],
    )
    reasons = [fan_in, pass_through, graph, baseline]
    timeline += [
        txn(110, 114, "A2217", "A5120", 36_000, prob=0.94, reasons=reasons[:2], case_id="C-0001"),
        txn(111, 116, "A2217", "A5121", 26_000, prob=0.91, reasons=reasons[:2], case_id="C-0001"),
        txn(112, 150, "A5120", "A9001", 35_500, rail=Rail.IMPS, prob=0.89, reasons=[graph], case_id="C-0001"),
        txn(113, 158, "A5121", "A9001", 25_700, rail=Rail.IMPS, prob=0.87, reasons=[graph], case_id="C-0001"),
    ]
    nodes = [GraphNode(id=v, label=v, role="victim", risk=0.1) for v in victims] + [
        GraphNode(id="A2217", label="A2217", role="mule", risk=0.94),
        GraphNode(id="A5120", label="A5120", role="mule", risk=0.89),
        GraphNode(id="A5121", label="A5121", role="mule", risk=0.87),
        GraphNode(id="A9001", label="A9001", role="collector", risk=0.9),
    ]
    edges = [GraphEdge(txn_id=t.txn_id, source=t.src_account, target=t.dst_account, amount=t.amount, ts=t.ts) for t in timeline]
    at_risk = 62_000
    return CaseDetail(
        case_id="C-0001",
        tier=Tier.CRITICAL,
        probability=0.94,
        amount_at_risk=at_risk,
        expected_loss=round(0.94 * at_risk, 2),
        accounts=len(nodes),
        transactions=len(timeline),
        typologies=["fan_in_out", "pass_through", "community"],
        opened_at=timeline[6].ts,
        updated_at=timeline[-1].ts,
        reasons=reasons,
        shap=[
            ShapValue(feature="distinct_senders_2h", value=7, contribution=1.42),
            ShapValue(feature="outflow_ratio_30m", value=0.90, contribution=1.18),
            ShapValue(feature="account_age_days", value=21, contribution=0.61),
            ShapValue(feature="pagerank_7d", value=0.034, contribution=0.44),
            ShapValue(feature="hour_of_day", value=16, contribution=-0.08),
        ],
        nodes=nodes,
        edges=edges,
        timeline=timeline,
        profiles=[
            AccountProfile(account_id="A2217", persona="student", opened_days_ago=21, median_amount_30d=450, txns_30d=31, devices=["D10"]),
            AccountProfile(account_id="A9001", persona="small_business", opened_days_ago=40, median_amount_30d=2_100, txns_30d=12, devices=["D44"]),
        ],
        narrative=(
            "Between 14:00 and 15:48, seven unrelated accounts paid a total of Rs 68,799 into A2217 (T000100 to T000106). "
            "Within six minutes of the last payment, A2217 forwarded Rs 62,000 to A5120 and A5121 (T000110, T000111), "
            "which passed it on to A9001 over IMPS (T000112, T000113). A2217 is 21 days old and normally receives one small "
            "payment a day. The pattern matches a mule chain collecting scam proceeds."
        ),
    )


def summaries(ring: CaseDetail) -> list[CaseSummary]:
    head = CaseSummary(**ring.model_dump(include=set(CaseSummary.model_fields)))
    return [
        head,
        CaseSummary(
            case_id="C-0002", tier=Tier.CRITICAL, probability=0.88, amount_at_risk=197_800, expected_loss=174_064,
            accounts=1, transactions=4, typologies=["cash_structuring"],
            opened_at=T0 - timedelta(days=4), updated_at=T0 - timedelta(hours=2),
        ),
        CaseSummary(
            case_id="C-0003", tier=Tier.REVIEW, probability=0.79, amount_at_risk=95_000, expected_loss=75_050,
            accounts=2, transactions=3, typologies=["device_takeover"],
            opened_at=T0 + timedelta(hours=11, minutes=12), updated_at=T0 + timedelta(hours=11, minutes=30),
        ),
        CaseSummary(
            case_id="C-0004", tier=Tier.WATCH, probability=0.61, amount_at_risk=120_000, expected_loss=73_200,
            accounts=2, transactions=1, typologies=["baseline_amount"],
            opened_at=T0 + timedelta(hours=2), updated_at=T0 + timedelta(hours=2),
        ),
    ]


def eval_report() -> EvalReport:
    return EvalReport(
        dataset="IBM AML HI-Small (sample)",
        split="time split: tune on first 70% of days, test on last 30%",
        generated_at=T0,
        overall=MetricRow(name="Ripple (full)", precision=0.41, recall=0.63, pr_auc=0.47, precision_at_50=0.58),
        baseline=MetricRow(name="Single-transaction baseline", precision=0.12, recall=0.31, pr_auc=0.14, precision_at_50=0.18),
        ablation=[
            MetricRow(name="Single-transaction baseline", precision=0.12, recall=0.31, pr_auc=0.14),
            MetricRow(name="Detectors only", precision=0.29, recall=0.44, pr_auc=0.30),
            MetricRow(name="+ behavioural baseline", precision=0.33, recall=0.50, pr_auc=0.36),
            MetricRow(name="+ graph layer", precision=0.37, recall=0.58, pr_auc=0.42),
            MetricRow(name="+ calibrated LightGBM", precision=0.41, recall=0.63, pr_auc=0.47),
        ],
        per_typology=[
            MetricRow(name=name, precision=p, recall=r)
            for name, p, r in [
                ("fan-in", 0.52, 0.77), ("fan-out", 0.49, 0.71), ("cycle", 0.44, 0.69), ("scatter-gather", 0.38, 0.58),
                ("gather-scatter", 0.36, 0.55), ("bipartite", 0.27, 0.41), ("stack", 0.25, 0.39), ("random", 0.14, 0.22),
            ]
        ],
        budget_curve=[
            BudgetPoint(alerts_per_day=k, recall=r, precision=p, value_caught_share=v)
            for k, r, p, v in [
                (10, 0.18, 0.71, 0.26), (25, 0.33, 0.64, 0.44), (50, 0.47, 0.58, 0.60),
                (100, 0.58, 0.47, 0.72), (200, 0.63, 0.41, 0.78), (400, 0.66, 0.29, 0.81),
            ]
        ],
        suggested_budget=100,
        throughput_tps=2_400,
        p95_latency_ms=18,
        notes=["Illustrative sample data, not measured results."],
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    ring = mule_ring()
    files = {
        "cases.json": [c.model_dump(mode="json") for c in summaries(ring)],
        "case_C-0001.json": ring.model_dump(mode="json"),
        "eval.json": eval_report().model_dump(mode="json"),
        "stream_sample.json": [StreamEvent(type="txn", txn=t).model_dump(mode="json", exclude_none=True) for t in ring.timeline],
    }
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote fixtures/{name}")


if __name__ == "__main__":
    main()
