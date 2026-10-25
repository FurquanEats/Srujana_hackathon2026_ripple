"""One-shot pattern learning: one confirmed trail that no detector caught becomes a detector that catches variants of
it, without flooding the queue with ordinary customers."""

import copy
import random

import pytest
from fastapi.testclient import TestClient

from ripple.api.main import create_app
from ripple.motifs import RelayTracker, learn
from ripple.redteam import ACTED_ON, Plan, RedTeam, transactions

EXAMPLE = Plan(victims=6, victim_amount=49_000, hops=2, split=4, delay_minutes=1440, pass_share=1.0, cash_out="atm")
# Other amounts, more hops and one victim fewer: one of the plans the adaptive red team found evading the engine.
VARIANT = Plan(victims=5, victim_amount=150_000, hops=4, split=4, delay_minutes=1440, pass_share=1.0, cash_out="atm")


@pytest.fixture(scope="module")
def team():
    return RedTeam(seed=11)


def run(engine, plan, tag, team, victims):
    engine = copy.deepcopy(engine)
    scored = [engine.process(t)[0] for t in transactions(plan, team.start, tag, victims, team.devices)]
    return engine, scored


def test_learns_from_one_missed_trail_and_catches_a_variant(team):
    rng = random.Random(1)
    learner, scored = run(team.base, EXAMPLE, "EX", team, rng.sample(team.victims, 6))
    assert max(s.probability for s in scored) < ACTED_ON  # the built-in detectors miss the example
    motif = learner.motifs.learn({s.txn_id for s in scored}, "test trail")
    assert motif.false_alarms_per_day <= 0.5
    assert len(motif.constraints) >= 3 and all(0 <= c.background_share <= 1 for c in motif.constraints)

    victims = rng.sample(team.victims, 5)
    _, missed = run(team.base, VARIANT, "VA", team, victims)
    assert max(s.probability for s in missed) < ACTED_ON  # the variant evades the engine on its own

    armed = copy.deepcopy(team.base)
    motif.deployed = True
    armed.motifs.motifs[motif.motif_id] = motif
    _, caught = run(armed, VARIANT, "VB", team, victims)
    flagged = [s for s in caught if s.probability >= ACTED_ON]
    assert flagged
    reason = next(r for r in flagged[0].reasons if r.code == f"motif:{motif.motif_id}")
    assert reason.counterfactual and flagged[0].txn_id in reason.txn_ids


def test_undeployed_motif_does_not_score(team):
    learner, scored = run(team.base, EXAMPLE, "EX", team, random.Random(2).sample(team.victims, 6))
    motif = learner.motifs.learn({s.txn_id for s in scored}, "test trail")
    armed = copy.deepcopy(team.base)
    armed.motifs.motifs[motif.motif_id] = motif
    _, scored = run(armed, VARIANT, "VC", team, random.Random(3).sample(team.victims, 5))
    assert not any(r.code.startswith("motif:") for s in scored for r in s.reasons)


def test_trail_without_a_relay_cannot_be_learned():
    with pytest.raises(ValueError, match="no account that received money"):
        learn(RelayTracker(), {"T1"}, "M1", "nothing")


def test_api_learns_from_a_victims_report_then_deploys(team):
    client = TestClient(create_app(source="engine", data=""))
    from ripple.sim.india import World

    world = World(n_people=80, n_shops=12, seed=11)  # the same bank the red team's engine was built from
    world.simulate(days=20)
    history = [row.txn for row in world.sorted_rows()]
    victims = random.Random(4).sample(team.victims, 6)
    example = transactions(EXAMPLE, team.start, "EX", victims, team.devices)
    client.post("/ingest", json=[t.model_dump(mode="json") for t in history + example])

    learned = client.post("/motifs/learn", json={"account": victims[0], "from_ts": team.start.isoformat()})
    assert learned.status_code == 200, learned.text
    body = learned.json()
    assert body["rules"] and not body["deployed"] and body["false_alarms_per_day"] <= 0.5

    deployed = client.post(f"/motifs/{body['motif_id']}/deploy").json()
    assert deployed["deployed"] and client.get("/motifs").json()[0]["motif_id"] == body["motif_id"]
    assert client.post("/motifs/learn", json={}).status_code == 422
    assert TestClient(create_app(source="fixtures")).get("/motifs").json() == []


def test_case_payments_stay_learnable_after_the_background_window():
    from datetime import datetime, timedelta

    from ripple.motifs import HISTORY
    from ripple.schema import Rail, Transaction

    tracker = RelayTracker()
    tracker.keep = lambda txn_id: txn_id == "T2"
    t0 = datetime(2026, 10, 1)
    pay = lambda i, ts, src, dst: Transaction(txn_id=f"T{i}", ts=ts, src_account=src, dst_account=dst, amount=1000,
                                              rail=Rail.IMPS)
    tracker.observe(pay(1, t0, "V", "M"))
    tracker.observe(pay(2, t0 + timedelta(hours=1), "M", "N"))  # a relay event the engine keeps for a case
    tracker.observe(pay(3, t0 + timedelta(hours=2), "M", "O"))  # an ordinary one
    tracker.observe(pay(4, t0 + HISTORY + timedelta(days=1), "P", "X"))
    tracker.observe(pay(5, t0 + HISTORY + timedelta(days=1, hours=1), "X", "Y"))  # a new event clears the old ones
    assert "T2" in tracker.by_txn and "T3" not in tracker.by_txn
    assert all(e.txn_id != "T2" for e in tracker.events)  # no longer part of the background
