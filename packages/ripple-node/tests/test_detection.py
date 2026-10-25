"""The red-flag rules on small, hand-checked ledgers, and the calibration that tunes them to a review budget."""

from __future__ import annotations

from datetime import datetime, timedelta

from ripple_core.clock import IST
from ripple_core.money import rupees
from ripple_node import detection
from ripple_node.detection import AccountFacts, Rule, Thresholds, Txn

T0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def facts(*txns: Txn, income: int | None = rupees(6_00_000), opened: datetime | None = None) -> AccountFacts:
    return AccountFacts("200000000001", "Test holder", opened or T0 - timedelta(days=400), income, txns)


def credit(txn: str, rupee: int, minute: float, sender: str = "BKAA0000001:1") -> Txn:
    return Txn(txn, at(minute), "credit", rupees(rupee), sender)


def debit(
    txn: str, rupee: int, minute: float, to: str | None = "BKCC0000001:9", exit_mode: str | None = None
) -> Txn:
    return Txn(txn, at(minute), "debit", rupees(rupee), None if exit_mode else to, exit_mode)


def rules(found: list[detection.Flag]) -> list[Rule]:
    return [f.rule for f in found]


def test_pass_through_cites_the_credit_and_the_debits_that_took_it() -> None:
    account = facts(credit("c1", 2_50_000, 0), debit("d1", 1_50_000, 2), debit("d2", 60_000, 3))
    [flag] = detection.pass_through(account, 30)
    assert flag.credit_txns == ("c1",)
    assert flag.cited_txns == ("c1", "d1", "d2")
    assert flag.amount == rupees(2_50_000)
    assert "84% of it left the account within 3 minutes in 2 debits" in flag.reason


def test_pass_through_respects_the_banks_setting() -> None:
    account = facts(credit("c1", 1_00_000, 0), debit("d1", 90_000, 45))
    assert detection.pass_through(account, 30) == []
    assert len(detection.pass_through(account, 60)) == 1


def test_credits_below_rs_1000_are_never_flagged() -> None:
    account = facts(credit("c1", 999, 0), debit("d1", 999, 1))
    assert detection.scan(account, Thresholds()) == []


def test_many_new_senders_counts_only_first_time_senders_in_24_hours() -> None:
    regulars = [
        credit(f"r{i}", 2_000, i - 60 * 48, sender="BKAA0000001:regular") for i in range(10)
    ]  # two days before
    newcomers = [credit(f"n{i}", 5_000, 60 + i, sender=f"BKAA0000001:{i}") for i in range(5)]
    [flag] = detection.many_new_senders(facts(*regulars, *newcomers), 5)
    assert flag.credit_txns == ("n0", "n1", "n2", "n3", "n4")
    assert "5 senders who had never paid this account before sent ₹25,000" in flag.reason


def test_many_new_senders_forgets_senders_outside_the_window() -> None:
    spread = [
        credit(f"n{i}", 5_000, i * 60 * 7, sender=f"BKAA0000001:{i}") for i in range(5)
    ]  # 7 hours apart
    assert detection.many_new_senders(facts(*spread), 5) == []


def test_out_of_profile_compares_30_days_of_credits_with_declared_income() -> None:
    account = facts(credit("c1", 60_000, 0), credit("c2", 1_00_000, 60 * 24), income=rupees(6_00_000))
    [flag] = detection.out_of_profile(account, 3.0)  # monthly Rs 50,000; Rs 1,60,000 is 3.2 times it
    assert flag.credit_txns == ("c1", "c2")
    assert "3.2 times the declared monthly income or turnover of ₹50,000" in flag.reason
    assert detection.out_of_profile(account, 5.0) == []


def test_out_of_profile_says_when_nothing_was_declared() -> None:
    assert detection.out_of_profile(facts(credit("c1", 5_000, 0), income=None), 3.0) == []
    [flag] = detection.out_of_profile(facts(credit("c1", 5_000, 0), income=0), 3.0)
    assert "declared no income or turnover" in flag.reason


def test_dormant_then_busy_needs_a_quiet_spell_and_a_large_credit() -> None:
    quiet = facts(credit("c1", 40_000, 0), opened=T0 - timedelta(days=120))
    [flag] = detection.dormant_then_busy(quiet, 90)
    assert "no transactions for 120 days" in flag.reason
    assert detection.dormant_then_busy(quiet, 180) == []
    small = facts(credit("c1", 10_000, 0), opened=T0 - timedelta(days=120))
    assert detection.dormant_then_busy(small, 90) == []


def test_quick_cash_out_needs_half_the_credit_in_cash() -> None:
    account = facts(
        credit("c1", 1_00_000, 0),
        debit("x1", 30_000, 10, exit_mode="atm"),
        debit("x2", 30_000, 20, exit_mode="atm"),
    )
    [flag] = detection.quick_cash_out(account, 60)
    assert flag.cited_txns == ("c1", "x1", "x2")
    assert "₹60,000 was withdrawn in cash in 2 withdrawals within 20 minutes" in flag.reason
    assert detection.quick_cash_out(account, 15) == []


def test_linked_to_reported_names_the_notice() -> None:
    account = facts(
        credit("c1", 5_000, 0, sender="BKBB0000001:mule"), debit("d1", 2_000, 5, to="BKBB0000001:mule")
    )
    found = detection.linked_to_reported(
        account, {"BKBB0000001:mule": "a CFCFRMS notice (acknowledgement 3)"}
    )
    assert [f.cited_txns for f in found] == [("c1",), ("d1",)]
    assert "from an account with a CFCFRMS notice" in found[0].reason
    assert found[1].amount == 0  # a payment out carries no credit to hold


def test_flag_keys_are_stable_so_a_rescan_never_duplicates() -> None:
    account = facts(credit("c1", 2_50_000, 0), debit("d1", 2_40_000, 2))
    first = detection.scan(account, Thresholds())
    again = detection.scan(account, Thresholds())
    assert [f.key for f in first] == [f.key for f in again]
    assert len({f.key for f in first}) == len(first)


def busy_shop(n: int) -> AccountFacts:
    """A genuine shop: many first-time customers, nothing leaves quickly."""
    sales = [credit(f"s{n}-{i}", 1_500, i * 30, sender=f"cust:{n}:{i}") for i in range(12)]
    return AccountFacts(f"SHOP{n}", "Shop", T0 - timedelta(days=400), rupees(60_00_000), tuple(sales))


def mule(n: int) -> AccountFacts:
    return AccountFacts(
        f"MULE{n}",
        "Mule",
        T0 - timedelta(days=400),
        rupees(2_40_000),
        (credit(f"m{n}", 2_00_000, 0), debit(f"md{n}", 1_95_000, 8)),
    )


def test_calibration_lays_out_each_setting_and_keeps_within_the_budget() -> None:
    accounts = [busy_shop(i) for i in range(6)] + [mule(i) for i in range(3)]
    result = detection.calibrate(
        accounts,
        {"MULE0", "MULE1", "MULE2"},
        since=T0 - timedelta(days=1),
        until=T0 + timedelta(days=29),
        budget_per_day=0.4,
    )
    assert result.within_budget
    assert result.expected_flags_per_day <= 0.4
    by_rule = {t.rule: t for t in result.tables}
    senders = by_rule[Rule.NEW_SENDERS]
    assert [r.accounts_flagged for r in senders.rows] == [0, 6, 6, 6]  # every shop at 10 or fewer senders
    assert (
        senders.chosen == 20
    )  # the busy shops would blow the budget, so the rule stays at its least sensitive
    pass_rows = by_rule[Rule.PASS_THROUGH].rows
    assert all(r.known_bad_flagged == 3 for r in pass_rows)
    assert result.proposal.pass_through_minutes == by_rule[Rule.PASS_THROUGH].chosen


def test_calibration_with_room_in_the_budget_goes_to_the_most_sensitive_setting() -> None:
    result = detection.calibrate(
        [mule(0)], {"MULE0"}, since=T0 - timedelta(days=1), until=T0 + timedelta(days=29), budget_per_day=100
    )
    assert result.proposal.pass_through_minutes == 180
    assert result.proposal.new_senders == 3


def test_calibration_says_when_even_the_least_sensitive_settings_exceed_the_budget() -> None:
    result = detection.calibrate(
        [mule(0)], {"MULE0"}, since=T0 - timedelta(days=1), until=T0 + timedelta(days=29), budget_per_day=0.01
    )
    assert not result.within_budget
    assert result.proposal.pass_through_minutes == 10
