"""The extra scam shapes: realistic limits, timings, and what the SOP's tracing rule finds in each mule account."""

from collections.abc import Mapping
from datetime import timedelta

import pytest

from ripple_core.messages import AccountOpening, ExitMode, LedgerPosting, Rail
from ripple_core.money import rupees
from ripple_core.tracing import AccountTrace, Direction, Entry, trace_account
from ripple_sim.scams import Scam
from ripple_sim.simulation import DEFAULT_MONTH, Simulation, simulate
from ripple_sim.traffic import TrafficConfig, month_days

UPI_CAP = rupees("1,00,000")
IMPS_CAP = rupees("5,00,000")


@pytest.fixture(scope="module")
def sim() -> Simulation:
    return simulate(seed=17, config=TrafficConfig(month=DEFAULT_MONTH, people_per_bank=6, shops_per_bank=2))


def scam(sim: Simulation, name: str) -> Scam:
    return next(s for s in sim.scams if s.name == name)


def ledger(sim: Simulation, s: Scam, role: str) -> tuple[int, list[LedgerPosting]]:
    account = s.accounts[role]
    opening = None
    postings: list[LedgerPosting] = []
    for d in sim.for_member(account.member.id):
        m = d.message
        if isinstance(m, AccountOpening) and m.account_number == account.number:
            opening = m.opening_balance
        elif isinstance(m, LedgerPosting) and m.account_number == account.number:
            postings.append(m)
    assert opening is not None
    return opening, postings


def trace(sim: Simulation, s: Scam, role: str, claims: Mapping[str, Mapping[str, int]]) -> AccountTrace:
    """Trace through one account; `claims` maps a payment reference to {ack number: paise of that claim}."""
    opening, postings = ledger(sim, s, role)
    entries = [Entry(p.txn_id, p.payment.at, Direction(p.direction), p.payment.amount) for p in postings]
    by_ref = {p.payment.reference: p.txn_id for p in postings if p.direction == "credit"}
    return trace_account(
        entries, opening_balance=opening, traced_in={by_ref[ref]: dict(c) for ref, c in claims.items()}
    )


def test_there_are_three_more_shapes(sim: Simulation) -> None:
    assert [s.name for s in sim.scams] == ["investment", "patient_mule", "task"]


def test_every_payment_respects_the_rail_limits(sim: Simulation) -> None:
    steps = [step for s in sim.scams for step in s.steps] + list(sim.story.steps)
    for step in steps:
        p = step.payment
        if p.rail is Rail.UPI:
            assert p.amount <= UPI_CAP, step.name
        if p.rail is Rail.IMPS:
            assert p.amount <= IMPS_CAP, step.name


def test_every_scam_runs_inside_the_month_and_is_reported_after_its_payments(sim: Simulation) -> None:
    days = set(month_days(DEFAULT_MONTH))
    for s in sim.scams:
        for step in s.steps:
            assert step.payment.at.date() in days, step.name
        for report in s.reports:
            assert report.reported_at.date() in days
            assert all(s.step(n).payment.at < report.reported_at for n in report.steps)


def test_scam_accounts_take_no_part_in_ordinary_traffic(sim: Simulation) -> None:
    refs = {step.payment.reference for s in sim.scams for step in s.steps}
    numbers = {a.number for s in sim.scams for a in s.accounts.values()}
    for d in sim.deliveries:
        m = d.message
        if isinstance(m, LedgerPosting) and m.account_number in numbers:
            assert m.payment.reference in refs


def test_the_investment_victim_pays_in_many_small_upi_transfers(sim: Simulation) -> None:
    s = scam(sim, "investment")
    (report,) = s.reports
    paid = [s.step(n) for n in report.steps]
    assert len(paid) == 14
    assert all(p.payment.rail is Rail.UPI and p.payment.amount <= UPI_CAP for p in paid)
    assert len({p.payment.at.date() for p in paid}) == 4
    for p in paid:  # each credit is forwarded within the hour
        forward = next(f for f in s.steps if f.payer == p.payee and f.payment.at > p.payment.at)
        assert forward.payment.at - p.payment.at < timedelta(hours=1)


def test_the_investment_mules_keep_only_their_commission_and_the_last_day_waits_at_the_exchange(
    sim: Simulation,
) -> None:
    s = scam(sim, "investment")
    (report,) = s.reports
    for mule in ("mule_a", "mule_b"):
        received = [s.step(n).payment for n in report.steps if s.step(n).payee == mule]
        forwarded = sum(st.payment.amount for st in s.steps if st.payer == mule)
        result = trace(sim, s, mule, {c.reference: {report.ack_number: c.amount} for c in received})
        assert result.remaining[report.ack_number] == sum(c.amount for c in received) - forwarded
        assert 0 < result.remaining[report.ack_number] < sum(c.amount for c in received) * 0.03
    exits = [st for st in s.steps if st.payer == "exchange"]
    assert len(exits) == 3
    _, postings = ledger(sim, s, "exchange")
    assert all(
        p.exit is not None and p.exit.mode is ExitMode.CRYPTO for p in postings if p.direction == "debit"
    )
    last = s.step("collector_to_exchange_day4").payment.amount
    balance = sum(p.payment.amount if p.direction == "credit" else -p.payment.amount for p in postings)
    assert balance == last > 0


def test_the_patient_mule_waits_hours_before_moving_money(sim: Simulation) -> None:
    s = scam(sim, "patient_mule")
    credit = s.step("victim_to_mule").payment
    first_debit = min(st.payment.at for st in s.steps if st.payer == "mule")
    assert first_debit - credit.at >= timedelta(hours=6)
    (report,) = s.reports
    result = trace(sim, s, "mule", {credit.reference: {report.ack_number: credit.amount}})
    assert result.remaining[report.ack_number] == rupees("1,20,000")
    assert result.own == rupees("3,200")


def test_the_task_scam_mixes_four_victims_in_one_shop_account(sim: Simulation) -> None:
    s = scam(sim, "task")
    assert len(s.reports) == 4
    assert len({r.ack_number for r in s.reports}) == 4
    claims = {
        s.step(n).payment.reference: {r.ack_number: s.step(n).payment.amount}
        for r in s.reports
        for n in r.steps
    }
    paid_in = sum(c for claim in claims.values() for c in claim.values())
    result = trace(sim, s, "shop", claims)
    sent_on = sum(st.payment.amount for st in s.steps if st.payer == "shop")
    assert sum(result.remaining.values()) == paid_in - sent_on  # victims' money leaves first
    assert sum(1 for v in result.remaining.values() if v > 0) >= 2  # more than one victim shares the hold
    assert result.own == rupees("38,500") + rupees("4,250")  # the shop's own money and its genuine takings
