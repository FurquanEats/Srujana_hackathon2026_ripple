"""India simulator: a legitimate base month, and injectors the engine catches (or, for Diwali, does not)."""

from datetime import timedelta

import pytest

from ripple.engine import Engine
from ripple.sim.india import INJECTORS, START, World, demo_world


@pytest.fixture(scope="module")
def scored():
    world = demo_world()
    engine = Engine("india")
    results = {row.txn.txn_id: (row, engine.process(row.txn)[0]) for row in world.sorted_rows()}
    return world, results


def test_base_month_is_labelled_legitimate_and_uses_indian_rails():
    world = World(n_people=20, n_shops=5)
    world.simulate(days=5)
    assert all(row.is_laundering == 0 and row.scenario == "" for row in world.rows)
    assert {row.txn.rail.value for row in world.rows} <= {"UPI", "IMPS", "NEFT", "RTGS", "CASH"}
    assert all(row.txn.currency == "INR" for row in world.rows)


def test_every_injector_returns_labelled_transactions_in_time_order():
    world = World(n_people=40, n_shops=8)
    world.simulate(days=3)
    for kind in INJECTORS:
        txns = world.inject(kind, START + timedelta(days=2))
        assert txns and txns == sorted(txns, key=lambda t: t.ts)
    with pytest.raises(ValueError):
        world.inject("bank_heist", START)


@pytest.mark.parametrize("kind", ["mule_ring", "scam_fanout", "sim_swap_takeover", "cash_structuring", "digital_arrest"])
def test_engine_alerts_on_each_fraud_scenario(scored, kind):
    _, results = scored
    alerts = [s for row, s in results.values() if row.scenario == kind and row.is_laundering and s.is_alert]
    assert alerts, f"no alert on {kind}"


def test_diwali_spike_mostly_stays_below_review(scored):
    _, results = scored
    diwali = [s for row, s in results.values() if row.scenario == "diwali_spike"]
    assert len(diwali) == 25
    assert sum(s.probability >= 0.70 for s in diwali) <= 2


def test_victim_flag_marks_first_hop_of_stolen_money(scored):
    world, _ = scored
    flagged = {}
    for row in world.rows:
        if row.victim_account:
            assert row.victim_account == row.txn.src_account
            flagged[row.scenario] = flagged.get(row.scenario, 0) + 1
    assert flagged == {"mule_ring": 7, "scam_fanout": 1, "sim_swap_takeover": 2, "digital_arrest": 2}
