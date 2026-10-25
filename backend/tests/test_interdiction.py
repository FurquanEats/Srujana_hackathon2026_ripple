"""Taint tracking and the freeze plan: where the stolen money is, and which accounts to freeze."""

import scenarios as s
from fastapi.testclient import TestClient

from ripple import fixtures
from ripple.api.main import create_app
from ripple.engine import Engine
from ripple.interdiction import plan


def engine_with(*builders):
    b = s.Builder()
    out = [f(b) for f in builders]
    engine = Engine()
    for t in b.sorted():
        engine.process(t)
    return engine, out


def plan_for(engine, txn_id):
    return plan(engine.detail(engine.log[txn_id].case_id))


def test_mule_ring_traces_every_victim_and_freezes_the_collector():
    engine, (ring,) = engine_with(s.mule_ring)
    p = plan_for(engine, ring["hop"][1])
    assert p.victims == ["V1", "V2", "V3", "V4", "V5", "V6", "V7"]
    assert p.stolen == 68799  # the mule's ordinary income from a known contact is not traced
    frozen = {f.account_id: f for f in p.freeze}
    assert frozen["A9001"].recoverable == 61200  # the collector holds what the two mules passed on
    assert "every observed path" in frozen["A9001"].reason  # it is the minimum cut
    assert p.recoverable_now == 67999 and p.escaped == 0
    assert p.recoverable_share_at_first_alert == 1.0


def test_money_paid_outside_the_trail_counts_as_escaped():
    b = s.Builder()
    ring = s.mule_ring(b)
    b.pay(b.txns[-1].ts.replace(minute=59), "A9001", "CASHOUT", 30000)
    engine = Engine()
    for t in b.sorted():
        engine.process(t)
    p = plan_for(engine, ring["hop"][1])
    assert p.recoverable_now + p.escaped <= p.stolen + 1


def test_cycle_starts_with_its_first_payment_and_freezes_where_money_returned():
    engine, (legs,) = engine_with(s.cycle)
    p = plan_for(engine, legs[-1])
    assert p.stolen == 200000 and [f.account_id for f in p.freeze][0] == "C1"


def test_cash_structuring_counts_every_cited_deposit():
    engine, (deposits,) = engine_with(s.cash_structuring)
    p = plan_for(engine, deposits[2])
    assert p.stolen == 49000 + 49500 + 48800 and p.victims == ["cash deposits"]


def test_timeline_never_traces_more_than_was_stolen():
    engine, (ring,) = engine_with(s.mule_ring)
    p = plan_for(engine, ring["hop"][1])
    assert all(pt.recoverable + pt.escaped <= p.stolen + 1 for pt in p.timeline)


def test_fixture_case_plan_and_api_route():
    assert plan(fixtures.case_detail("C-0001")).recoverable_now == 67999
    client = TestClient(create_app(source="fixtures"))
    body = client.get("/cases/C-0001/interdiction").json()
    assert body["freeze"][0]["account_id"] == "A9001"
    assert client.get("/cases/C-9999/interdiction").status_code == 404


def test_digital_arrest_case_treats_the_customer_as_victim_and_counts_cash_outs():
    from datetime import timedelta

    from ripple import trace
    from ripple.sim.india import START, World

    world = World(n_people=60, n_shops=10)
    world.simulate(days=20)
    world.inject("digital_arrest", START + timedelta(days=18))
    engine = Engine("india")
    for row in world.sorted_rows():
        engine.process(row.txn)
    victim = next(row.victim_account for row in world.rows if row.victim_account)
    case = next(c for c in engine.cases.cases.values() if victim in c.accounts and "coerced_transfer" in c.typologies)
    detail = engine.detail(case.case_id)
    first = plan(detail)
    holders = {h.account_id for h in first.holdings}
    trail = [t for t in detail.timeline if t.dst_account in holders or t.src_account in holders]
    p = plan(detail, onward=trace.onward(engine, trail))
    assert p.victims == [victim] and victim not in {f.account_id for f in p.freeze}
    assert p.stolen == 750000 + 390000
    assert p.escaped == 95000 + 245000 + 150000  # ATM withdrawal and two crypto purchases


def _txn(i, minute, src, dst, amount):
    from datetime import datetime

    from ripple.schema import Layer, Rail, ScoredTransaction

    return ScoredTransaction(txn_id=f"R{i}", ts=datetime(2026, 10, 20, 12, minute), src_account=src, dst_account=dst,
                             amount=amount, rail=Rail.IMPS, probability=0.9, confidence=1.0,
                             layer_scores={layer: 0.0 for layer in Layer}, is_alert=True)


def test_three_tracing_rules_give_a_hold_range_when_own_money_is_mixed_in():
    """A mule receives Rs 50,000 stolen, then Rs 20,000 of its own salary, then withdraws Rs 30,000."""
    from datetime import datetime

    from ripple.interdiction import plan_trail

    trail = [_txn(1, 0, "VICTIM", "MULE", 50_000), _txn(2, 20, "MULE", "ATM-1", 30_000)]
    salary = [(datetime(2026, 10, 20, 12, 10), "MULE", 20_000.0, "SAL1")]
    p = plan_trail("T", trail, [], own_funds=salary)
    mule = next(f for f in p.freeze if f.account_id == "MULE")
    # Haircut: 30,000 leaves carrying 50/70 of it. FIFO: the stolen money arrived first, so it leaves first.
    # LIBR: the salary is spent first, so 40,000 of the stolen money is still there.
    assert mule.by_rule == {"haircut": 28_571.43, "fifo": 20_000.0, "libr": 40_000.0}
    assert (mule.hold_low, mule.hold_high) == (20_000.0, 40_000.0)
    assert mule.recoverable == 28_571.43 and p.recoverable_low == 20_000.0 and p.recoverable_high == 40_000.0


def test_libr_never_refills_traced_money_from_later_deposits():
    from datetime import datetime

    from ripple.interdiction import plan_trail

    trail = [_txn(1, 0, "VICTIM", "MULE", 50_000), _txn(2, 10, "MULE", "ATM-1", 45_000)]
    later = [(datetime(2026, 10, 20, 12, 30), "MULE", 20_000.0, "SAL1")]
    p = plan_trail("T", trail, [], datetime(2026, 10, 20, 13, 0), own_funds=later)
    mule = next(f for f in p.freeze if f.account_id == "MULE")
    assert mule.by_rule["libr"] == 5_000.0 and mule.hold_low == mule.hold_high == 5_000.0


def test_money_spent_at_a_shop_has_left_the_trail_and_the_shop_is_never_held():
    from ripple.interdiction import plan_trail

    trail = [_txn(1, 0, "VICTIM", "MULE", 50_000), _txn(2, 10, "MULE", "SHOP01", 2_000)]
    p = plan_trail("T", trail, [], merchants=frozenset({"SHOP01"}))
    assert "SHOP01" not in {f.account_id for f in p.freeze} | {h.account_id for h in p.holdings}
    assert p.escaped == 2_000 and p.recoverable_now == 48_000
