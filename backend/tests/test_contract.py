"""The fixtures are the frontend's contract: they must always validate against ripple.schema."""

from ripple import fixtures


def test_cases_fixture_validates():
    cases = fixtures.cases()
    assert cases, "cases.json is empty"
    assert all(c.expected_loss <= c.amount_at_risk for c in cases)


def test_case_detail_is_consistent():
    case = fixtures.case_detail("C-0001")
    assert case is not None
    txn_ids = {t.txn_id for t in case.timeline}
    node_ids = {n.id for n in case.nodes}
    for reason in case.reasons:
        assert set(reason.txn_ids) <= txn_ids, f"{reason.code} cites a transaction not in the case"
    for edge in case.edges:
        assert {edge.source, edge.target} <= node_ids


def test_eval_fixture_validates():
    report = fixtures.eval_report()
    assert report.ablation[0].name == report.baseline.name
