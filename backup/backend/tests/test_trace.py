"""Golden-hour trace from a victim's report, and the demo routes that inject scenarios and trace them."""

from datetime import timedelta

from fastapi.testclient import TestClient

from ripple.api.main import create_app
from ripple.engine import Engine
from ripple.sim.india import START, World
from ripple.trace import trace


def digital_arrest_world():
    world = World(n_people=60, n_shops=10)
    world.simulate(days=5)
    before = len(world.rows)
    world.inject("digital_arrest", START + timedelta(days=4))
    victim = next(row for row in world.rows[before:] if row.victim_account)
    return world, victim


def test_trace_follows_the_victims_money_to_mules_cash_and_crypto():
    world, victim = digital_arrest_world()
    engine = Engine("india")
    for row in world.sorted_rows():
        engine.process(row.txn)
    plan = trace(engine, victim.victim_account, victim.txn.ts - timedelta(minutes=1))
    assert plan is not None and plan.victims == [victim.victim_account]
    assert plan.stolen == 750000 + 390000  # both RTGS transfers to "safe accounts"
    assert plan.escaped > 0  # the ATM withdrawal and the crypto purchases have left
    assert plan.recoverable_now > 0 and plan.freeze
    assert plan.recoverable_now + plan.escaped <= plan.stolen + 1
    frozen = {f.account_id for f in plan.freeze}
    assert not any(a.startswith(("ATM", "P2P-")) for a in frozen)  # money at a cash-out is gone, not frozen


def test_trace_route_and_unknown_account():
    world, victim = digital_arrest_world()
    client = TestClient(create_app(source="engine", data=""))
    client.post("/ingest", json=[row.txn.model_dump(mode="json") for row in world.sorted_rows()])
    body = client.post("/trace", json={"account": victim.victim_account,
                                       "from_ts": (victim.txn.ts - timedelta(minutes=1)).isoformat()}).json()
    assert body["case_id"] == f"trace-{victim.victim_account}" and body["freeze"]
    assert client.post("/trace", json={"account": "NOBODY"}).status_code == 404


def test_inject_route_adds_a_scenario_to_the_live_feed():
    with TestClient(create_app(source="engine", data="sim:india", speed=0)) as client:
        body = client.post("/inject/digital_arrest").json()
        assert body["kind"] == "digital_arrest" and body["txn_ids"] and body["victim_account"]
        assert client.post("/inject/bank_heist").status_code == 404
    assert TestClient(create_app(source="fixtures")).post("/inject/mule_ring").status_code == 409
