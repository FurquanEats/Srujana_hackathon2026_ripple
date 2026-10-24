"""The engine end to end: cases, tiers, graph layer, feedback and speed."""

import scenarios as s

from ripple import feedback
from ripple.engine import Engine
from ripple.schema import Layer, Tier


def build():
    b = s.Builder()
    ring = s.mule_ring(b)
    legit = s.legit_big_payment(b)
    deposits = s.cash_structuring(b)
    engine = Engine()
    for t in b.sorted():
        engine.process(t)
    return engine, ring, legit, deposits


def case_of(engine, txn_id):
    return engine.cases.get(engine.log[txn_id].case_id)


def test_mule_ring_becomes_one_critical_case():
    engine, ring, _, _ = build()
    case = case_of(engine, ring["hop"][1])
    assert case is case_of(engine, ring["out"][1])
    summary = engine.cases.summary(case)
    assert summary.tier == Tier.CRITICAL
    assert {"A2217", "A5120", "A5121", "A9001"} <= case.accounts
    assert summary.amount_at_risk == 62000  # the most any one account moved, not every hop added up
    assert {"pass_through", "fan_in_out"} <= set(summary.typologies)


def test_queue_puts_tiers_first_and_legit_payment_is_watch_below_the_ring():
    engine, ring, legit, _ = build()
    ranked = [c.case_id for c in engine.cases.ranked()]
    assert engine.cases.summary(case_of(engine, legit)).tier == Tier.WATCH
    assert ranked.index(case_of(engine, ring["hop"][1]).case_id) < ranked.index(case_of(engine, legit).case_id)


def test_structuring_case_counts_every_cited_deposit():
    engine, _, _, deposits = build()
    summary = engine.cases.summary(case_of(engine, deposits[2]))
    assert summary.amount_at_risk == 49000 + 49500 + 48800
    assert summary.tier == Tier.REVIEW


def test_cash_deposits_do_not_link_unrelated_cases():
    engine, ring, _, deposits = build()
    assert case_of(engine, deposits[2]).accounts == {"A3141"}


def test_case_detail_is_self_consistent():
    engine, ring, _, _ = build()
    detail = engine.detail(engine.log[ring["hop"][1]].case_id)
    timeline = {t.txn_id for t in detail.timeline}
    assert set(ring["in"]) <= timeline  # the payments that fed the mule are shown as context
    nodes = {n.id for n in detail.nodes}
    assert all({e.source, e.target} <= nodes for e in detail.edges)
    roles = {n.id: n.role for n in detail.nodes}
    assert roles["A2217"] == "mule" and roles["A9001"] == "collector"
    assert all(r.txn_ids for r in detail.reasons if r.layer == Layer.DETECTOR)


def test_graph_layer_scores_ring_after_recompute():
    engine, ring, _, _ = build()
    engine.graph.recompute()
    score, reason = engine.graph.account_score("A9001")
    assert score > 0 and reason is not None and reason.code == "community"


def test_feedback_confirm_and_dismiss():
    engine, ring, legit, _ = build()
    ring_case = engine.log[ring["hop"][1]].case_id
    result = feedback.apply(engine, ring_case, "confirmed")
    assert result.weights_after[Layer.DETECTOR] > result.weights_before[Layer.DETECTOR]
    assert engine.cases.get(ring_case).status == "confirmed"
    assert {"A2217", "A9001"} <= engine.graph.confirmed

    legit_case = engine.log[legit].case_id
    feedback.apply(engine, legit_case, "dismissed")
    assert ("S1", "JEWELLER") in engine.dismissed
    assert legit_case not in {c.case_id for c in engine.cases.ranked()}


def test_scoring_is_fast():
    engine, _, _, _ = build()
    assert engine.stats()["p95_latency_ms"] < 50
