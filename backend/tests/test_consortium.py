"""Consortium: banks share only keyed hashes of flagged accounts, and a cross-bank flag becomes context."""

from datetime import datetime, timedelta

from ripple.consortium import Consortium, Hub, bank_of
from ripple.schema import Rail, Transaction


def test_hub_stores_no_account_numbers_and_ignores_the_reporting_bank():
    hub = Hub(b"k")
    t = datetime(2026, 10, 1)
    hub.report("A", "A:123", t)
    assert "A:123" not in str(hub.flags)
    assert hub.flagged_elsewhere("A", "A:123", t) == []
    assert hub.flagged_elsewhere("B", "A:123", t + timedelta(hours=1)) == ["A"]
    assert hub.flagged_elsewhere("B", "A:123", t + timedelta(days=4)) == []


def test_bank_of_reads_ibm_style_ids():
    assert bank_of("0011:8000ABC") == "0011" and bank_of("0011-8000ABC") == "0011"


def test_a_flag_at_one_bank_becomes_a_reason_at_another():
    con = Consortium(["A", "B"])
    t0 = datetime(2022, 9, 1)
    # Bank A's mule collects from new senders and forwards almost everything to an account at bank B.
    pay = lambda i, minutes, src, dst, amt: Transaction(txn_id=f"T{i}", ts=t0 + timedelta(minutes=minutes),  # noqa: E731
                                                        src_account=src, dst_account=dst, amount=amt,
                                                        currency="USD", rail=Rail.ACH)
    n = 0
    for day in range(3):  # history so the engines are past their warm-up
        for k in range(5):
            n += 1
            con.process(pay(n, day * 1440 + k * 60, f"A:shop{k}", f"A:cust{k}", 50))
    start = 3 * 1440
    for i in range(6):
        n += 1
        con.process(pay(n, start + i * 10, f"X:v{i}", "A:mule", 1000))
    n += 1
    con.process(pay(n, start + 65, "A:mule", "B:collector", 5800))
    n += 1
    later = con.process(pay(n, start + 200, "B:collector", "B:friend", 100))
    assert "consortium" in {r.code for r in later["B"].reasons}
    alone = Consortium(["A", "B"], sharing=False)
    assert alone.hub.flags == {}
