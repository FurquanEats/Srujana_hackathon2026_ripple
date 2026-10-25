from datetime import datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ripple_core.clock import IST
from ripple_core.money import rupees
from ripple_core.tracing import Direction, Entry, LedgerError, Lien, trace_account

CREDIT, DEBIT = Direction.CREDIT, Direction.DEBIT


def at(day: int, hhmm: str) -> datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime(2024, 12, day, hour, minute, tzinfo=IST)


def test_annexure_v_illustration_1_attributes_by_time_order() -> None:
    """SOP Annexure V, illustration 1: A's and most of B's money left; C's is all still there."""
    entries = [
        Entry("a", at(15, "13:02"), CREDIT, rupees(97_000)),
        Entry("d1", at(15, "13:09"), DEBIT, rupees(97_000)),
        Entry("b", at(15, "14:17"), CREDIT, rupees(58_000)),
        Entry("d2", at(15, "14:22"), DEBIT, rupees(50_000)),
        Entry("c", at(15, "15:11"), CREDIT, rupees(150_000)),
    ]
    traced_in = {"a": {"A": rupees(97_000)}, "b": {"B": rupees(58_000)}, "c": {"C": rupees(150_000)}}

    trace = trace_account(entries, opening_balance=rupees(873), traced_in=traced_in)

    assert trace.remaining == {"A": 0, "B": rupees(8_000), "C": rupees(150_000)}
    assert trace.own == rupees(873)
    assert trace.balance == rupees("1,58,873")


def test_annexure_v_illustration_2_splits_pro_rata() -> None:
    """SOP Annexure V, illustration 2: one debit after five victims' credits; the SOP's own release figures."""
    victim_credits = [
        ("V", "12:20", 85_326),
        ("W", "12:51", 38_443),
        ("X", "13:23", 50_000),
        ("Y", "13:55", 50_000),
        ("Z", "14:30", 30_000),
    ]
    entries = [Entry(v, at(15, t), CREDIT, rupees(a)) for v, t, a in victim_credits]
    entries.append(Entry("debit", at(15, "15:06"), DEBIT, rupees(47_226)))
    traced_in = {v: {v: rupees(a)} for v, _, a in victim_credits}

    trace = trace_account(entries, opening_balance=0, traced_in=traced_in)

    assert trace.remaining == {
        "X": rupees("40,695.08"),
        "V": rupees("69,446.97"),
        "Y": rupees("40,695.08"),
        "Z": rupees("24,417.05"),
        "W": rupees("31,288.82"),
    }
    assert trace.own == 0


def test_demo_story_mule_m3() -> None:
    """The PRD's demo story: victim money leaves first, so the salary paid afterwards is traced at Rs 0."""
    t0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
    entries = [
        Entry("in", t0, CREDIT, rupees(250_000)),
        Entry("ravi", t0 + timedelta(minutes=2), DEBIT, rupees(200_000)),
        Entry("galaxy", t0 + timedelta(minutes=3), DEBIT, rupees(120_000)),
        Entry("salary", t0 + timedelta(minutes=5), DEBIT, rupees(15_000)),
    ]
    ack = "31234567890123"

    trace = trace_account(entries, opening_balance=rupees(300_000), traced_in={"in": {ack: rupees(250_000)}})

    carried = {d.txn_id: d.traced for d in trace.debits}
    assert carried == {"ravi": rupees(200_000), "galaxy": rupees(50_000), "salary": 0}
    assert trace.traced_remaining == 0
    assert trace.own == rupees(215_000)


def test_partly_traced_credit_counts_the_rest_as_own_money() -> None:
    t0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
    entries = [
        Entry("in", t0, CREDIT, rupees(1_000)),
        Entry("out", t0 + timedelta(minutes=1), DEBIT, rupees(700)),
    ]

    trace = trace_account(entries, opening_balance=0, traced_in={"in": {"A": rupees(400)}})

    assert trace.debits[0].carried == {"A": rupees(400)}
    assert trace.own == rupees(300)


def test_as_of_ignores_later_entries() -> None:
    t0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
    entries = [
        Entry("in", t0, CREDIT, rupees(500)),
        Entry("out", t0 + timedelta(hours=1), DEBIT, rupees(500)),
    ]

    trace = trace_account(entries, opening_balance=0, traced_in={"in": {"A": rupees(500)}}, as_of=t0)

    assert trace.remaining == {"A": rupees(500)}
    assert trace.debits == ()


def test_a_lien_sets_victim_money_aside() -> None:
    """After a lien, the holder's later payments come out of their own money, not the victim's."""
    t0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
    entries = [
        Entry("in", t0, CREDIT, rupees(1_000)),
        Entry("salary", t0 + timedelta(minutes=5), CREDIT, rupees(500)),
        Entry("out", t0 + timedelta(minutes=10), DEBIT, rupees(400)),
    ]
    lien = Lien(t0 + timedelta(minutes=1), "A", rupees(1_000))

    trace = trace_account(entries, opening_balance=0, traced_in={"in": {"A": rupees(1_000)}}, liens=[lien])

    assert trace.remaining == {"A": rupees(1_000)}
    assert trace.debits[0].carried == {}
    assert trace.own == rupees(100)
    with pytest.raises(LedgerError, match="not under a lien"):
        trace_account(
            [*entries, Entry("big", t0 + timedelta(minutes=11), DEBIT, rupees(200))],
            opening_balance=0,
            traced_in={"in": {"A": rupees(1_000)}},
            liens=[lien],
        )


def test_overdrawn_ledger_is_rejected() -> None:
    t0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
    with pytest.raises(LedgerError, match="larger than the balance"):
        trace_account([Entry("out", t0, DEBIT, rupees(1))], opening_balance=0, traced_in={})


def test_tracing_more_than_the_credit_is_rejected() -> None:
    t0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
    with pytest.raises(LedgerError, match="more is traced"):
        trace_account(
            [Entry("in", t0, CREDIT, rupees(10))], opening_balance=0, traced_in={"in": {"A": rupees(11)}}
        )


def test_naive_times_and_bad_amounts_are_rejected() -> None:
    with pytest.raises(LedgerError, match="timezone-aware"):
        Entry("x", datetime(2026, 1, 1), CREDIT, 1)  # noqa: DTZ001 - checking that naive times are refused
    with pytest.raises(LedgerError, match="positive"):
        Entry("x", datetime(2026, 1, 1, tzinfo=IST), CREDIT, 0)


# Property tests: the rules that must hold for any ledger.

CLAIMS = ("2" + "0" * 13, "3" + "1" * 13, "3" + "2" * 13)


@st.composite
def ledgers(draw: st.DrawFn) -> tuple[list[Entry], int, dict[str, dict[str, int]]]:
    opening = draw(st.integers(0, 10_000_000))
    balance = opening
    t0 = datetime(2026, 10, 20, 9, 0, tzinfo=IST)
    entries: list[Entry] = []
    traced_in: dict[str, dict[str, int]] = {}
    for i in range(draw(st.integers(0, 25))):
        when = t0 + timedelta(minutes=i)
        if balance > 0 and draw(st.booleans()):
            amount = draw(st.integers(1, balance))
            entries.append(Entry(f"t{i}", when, DEBIT, amount))
            balance -= amount
        else:
            amount = draw(st.integers(1, 5_000_000))
            entries.append(Entry(f"t{i}", when, CREDIT, amount))
            balance += amount
            claims = draw(st.lists(st.sampled_from(CLAIMS), max_size=2, unique=True))
            if claims and amount >= len(claims):
                cut = draw(st.integers(len(claims), amount))
                share = cut // len(claims)
                traced_in[f"t{i}"] = dict.fromkeys(claims, share)
    return entries, opening, traced_in


@given(ledgers())
def test_money_is_conserved(ledger: tuple[list[Entry], int, dict[str, dict[str, int]]]) -> None:
    entries, opening, traced_in = ledger
    trace = trace_account(entries, opening_balance=opening, traced_in=traced_in)

    credited = sum(e.amount for e in entries if e.direction is CREDIT)
    debits = sum(e.amount for e in entries if e.direction is DEBIT)
    assert trace.balance == opening + credited - debits
    traced_total = sum(sum(v.values()) for v in traced_in.values())
    assert trace.traced_remaining + sum(d.traced for d in trace.debits) == traced_total
    assert all(p >= 0 for p in trace.remaining.values())
    assert trace.own >= 0


@given(ledgers())
def test_victim_money_leaves_before_own_money(
    ledger: tuple[list[Entry], int, dict[str, dict[str, int]]],
) -> None:
    entries, opening, traced_in = ledger
    trace = trace_account(entries, opening_balance=opening, traced_in=traced_in)

    victims_before = 0
    by_id = {d.txn_id: d for d in trace.debits}
    for e in sorted(entries, key=lambda e: e.at):
        if e.direction is CREDIT:
            victims_before += sum(traced_in.get(e.txn_id, {}).values())
            continue
        d = by_id[e.txn_id]
        assert d.traced == min(e.amount, victims_before)
        assert all(p > 0 for p in d.carried.values())
        victims_before -= d.traced
