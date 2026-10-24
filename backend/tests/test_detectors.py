"""Each detector: one hit, one near-miss just past its threshold, and behaviour with missing data."""

from datetime import timedelta

import pytest
import scenarios as s

from ripple.engine import Engine
from ripple.schema import Rail


def run(b: s.Builder) -> dict:
    engine = Engine()
    return {t.txn_id: engine.process(t)[0] for t in b.sorted()}


def codes(scored) -> set[str]:
    return {r.code for r in scored.reasons}


def test_pass_through_hits_mule_and_cites_transactions():
    b = s.Builder()
    ring = s.mule_ring(b)
    out = run(b)
    hop = out[ring["hop"][0]]
    assert "pass_through" in codes(hop)
    reason = next(r for r in hop.reasons if r.code == "pass_through")
    assert ring["out"][0] in reason.txn_ids and ring["hop"][0] in reason.txn_ids
    assert reason.counterfactual


def test_pass_through_near_miss_when_less_than_80_percent_forwarded():
    b = s.Builder()
    b.history("A1")
    t = s.RING_DAY + timedelta(hours=5)
    b.pay(t, "STRANGER", "A1", 40000)
    last = b.pay(t + timedelta(minutes=10), "A1", "A2", 30000)  # 75%
    assert "pass_through" not in codes(run(b)[last.txn_id])


def test_pass_through_ignores_salary_from_a_known_employer():
    b = s.Builder()
    rent = s.salary_then_rent(b)
    assert "pass_through" not in codes(run(b)[rent])


def test_fan_in_out_hit_and_near_miss():
    b = s.Builder()
    ring = s.mule_ring(b)
    assert "fan_in_out" in codes(run(b)[ring["out"][1]])

    b = s.Builder()
    b.history("A1")
    t = s.RING_DAY + timedelta(hours=5)
    for i in range(4):  # one sender short
        b.pay(t + timedelta(minutes=10 * i), f"V{i}", "A1", 10000)
    last = b.pay(t + timedelta(minutes=45), "A1", "A2", 38000)
    assert "fan_in_out" not in codes(run(b)[last.txn_id])


def test_fan_out_burst_hit_and_near_miss():
    b = s.Builder()
    last = s.fan_out(b)
    assert "fan_out_burst" in codes(run(b)[last])

    b = s.Builder()
    b.history("F1")
    t = s.RING_DAY + timedelta(hours=6)
    last = [b.pay(t + timedelta(minutes=7 * i), "F1", f"NEW{i}", 9000) for i in range(4)][-1]
    assert "fan_out_burst" not in codes(run(b)[last.txn_id])


def test_scatter_gather_hit_and_near_miss():
    b = s.Builder()
    ids = s.scatter_gather(b)
    assert "scatter_gather" in codes(run(b)[ids[-1]])

    b = s.Builder()
    for a in ("G0", "G1", "G2", "G9"):
        b.history(a)
    t = s.RING_DAY + timedelta(hours=2)
    for i, m in enumerate(("G1", "G2")):  # only two intermediaries
        b.pay(t + timedelta(minutes=10 * i), "G0", m, 50000)
        last = b.pay(t + timedelta(hours=4, minutes=10 * i), m, "G9", 49000)
    assert "scatter_gather" not in codes(run(b)[last.txn_id])


def test_temporal_cycle_hit_slow_cycle_miss_and_refund_ignored():
    b = s.Builder()
    legs = s.cycle(b)
    out = run(b)
    reason = next(r for r in out[legs[-1]].reasons if r.code == "temporal_cycle")
    assert set(legs) <= set(reason.txn_ids)

    b = s.Builder()
    for a in ("C1", "C2", "C3"):
        b.history(a)
    t = s.RING_DAY
    b.pay(t, "C1", "C2", 100000)
    b.pay(t + timedelta(hours=40), "C2", "C3", 99000)
    slow = b.pay(t + timedelta(hours=80), "C3", "C1", 98000)  # beyond the 72-hour window: a known miss
    assert "temporal_cycle" not in codes(run(b)[slow.txn_id])

    b = s.Builder()
    b.history("C1")
    b.pay(s.RING_DAY, "C1", "SHOP", 5000)
    refund = b.pay(s.RING_DAY + timedelta(hours=2), "SHOP", "C1", 5000)
    assert "temporal_cycle" not in codes(run(b)[refund.txn_id])


def test_cash_structuring_hit_and_threshold_edges():
    b = s.Builder()
    deposits = s.cash_structuring(b)
    out = run(b)
    assert "cash_structuring" not in codes(out[deposits[1]])  # two deposits are not a pattern yet
    assert "cash_structuring" in codes(out[deposits[2]])

    b = s.Builder()
    b.history("A3141")
    last = [b.pay(s.RING_DAY + timedelta(days=i), "CASH", "A3141", 50001, rail=Rail.CASH) for i in range(4)][-1]
    assert "cash_structuring" not in codes(run(b)[last.txn_id])  # above the limit, so PAN is quoted anyway


def test_ctr_reportable_fires_once_when_month_crosses_10_lakh():
    b = s.Builder()
    b.history("A7")
    deps = [b.pay(s.RING_DAY + timedelta(hours=i), "CASH", "A7", 300000, rail=Rail.CASH) for i in range(5)]
    out = run(b)
    hits = [d.txn_id for d in deps if "ctr_reportable" in codes(out[d.txn_id])]
    assert hits == [deps[3].txn_id]


def test_device_takeover_hit_and_misses():
    b = s.Builder()
    tid = s.device_takeover(b)
    assert "device_takeover" in codes(run(b)[tid])

    b = s.Builder()
    b.history("U1", low=200, high=4000)
    b.pay(s.RING_DAY + timedelta(hours=1), "U1", "M-U1-0", 150, device="D88")
    late = b.pay(s.RING_DAY + timedelta(hours=4), "U1", "X-NEW", 95000, device="D88")  # device in use for 3 hours
    assert "device_takeover" not in codes(run(b)[late.txn_id])


def test_missing_device_lowers_confidence_not_risk():
    b = s.Builder()
    b.history("U2")
    with_device = b.pay(s.RING_DAY, "U2", "M-U2-0", 800)
    without = b.pay(s.RING_DAY + timedelta(minutes=5), "U2", "M-U2-0", 800, device=None, location=None)
    out = run(b)
    assert out[without.txn_id].confidence < out[with_device.txn_id].confidence
    assert out[without.txn_id].probability <= out[with_device.txn_id].probability + 1e-6


@pytest.mark.parametrize("amount", [120000])
def test_legit_big_payment_stays_watch(amount):
    b = s.Builder()
    tid = s.legit_big_payment(b)
    scored = run(b)[tid]
    assert scored.layer_scores["baseline"] > 0.9
    assert scored.probability < 0.70  # can reach Watch, never Review or Critical, without corroboration


def test_fan_out_burst_ignores_a_business_that_always_pays_new_payees():
    b = s.Builder()
    for d in range(21):  # a payroll-like account paying 6 new people every day
        for i in range(6):
            b.pay(s.T0 + d * s.DAY + timedelta(hours=10, minutes=5 * i), "PAYROLL", f"EMP{d}-{i}", 20000)
    last = [b.pay(s.RING_DAY + timedelta(hours=10, minutes=5 * i), "PAYROLL", f"NEWEMP{i}", 20000) for i in range(6)][-1]
    assert "fan_out_burst" not in codes(run(b)[last.txn_id])
