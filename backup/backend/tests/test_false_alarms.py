"""A legitimate simulated month (salaries, gig payouts, rent, shops banking cash and paying suppliers, Diwali
shopping) must stay quiet: unusual payments may reach Watch, but almost nothing legitimate reaches Review."""

import pytest

from ripple.engine import Engine
from ripple.sim.india import demo_world


@pytest.fixture(scope="module")
def results():
    world = demo_world()
    engine = Engine("india")
    return [(row, engine.process(row.txn)[0]) for row in world.sorted_rows()]


def test_legitimate_rows_rarely_reach_review(results):
    legit = [s for row, s in results if not row.is_laundering]
    above_watch = [s for s in legit if s.probability >= 0.70]
    assert len(above_watch) <= 10, [r.text for s in above_watch[:5] for r in s.reasons[:1]]


def test_every_fraud_scenario_still_reaches_review_or_critical(results):
    reached = {row.scenario for row, s in results if row.is_laundering and s.probability >= 0.70}
    assert reached >= {"mule_ring", "scam_fanout", "sim_swap_takeover", "cash_structuring", "digital_arrest"}
