from collections import Counter, defaultdict
from datetime import date

import pytest

from ripple_core.messages import AccountRef, ExitMode, Rail
from ripple_core.tracing import Direction
from ripple_sim.events import AccountOpening, ExitDetail, LedgerPosting
from ripple_sim.network import NETWORK, member
from ripple_sim.simulation import Simulation, simulate
from ripple_sim.traffic import TrafficConfig, month_days

MONTH = date(2026, 11, 1)
CONFIG = TrafficConfig(month=MONTH, people_per_bank=20, shops_per_bank=3)


@pytest.fixture(scope="module")
def sim() -> Simulation:
    return simulate(seed=3, config=CONFIG)


def postings(sim: Simulation) -> list[tuple[str, LedgerPosting]]:
    return [(d.member, d.message) for d in sim.deliveries if isinstance(d.message, LedgerPosting)]


def test_a_seed_always_gives_the_same_month() -> None:
    a = simulate(seed=5, config=CONFIG)
    b = simulate(seed=5, config=CONFIG)
    c = simulate(seed=6, config=CONFIG)
    assert [d.model_dump() for d in a.deliveries] == [d.model_dump() for d in b.deliveries]
    assert [d.model_dump() for d in a.deliveries] != [d.model_dump() for d in c.deliveries]


def test_deliveries_are_in_time_order_with_rising_transaction_ids(sim: Simulation) -> None:
    times = [d.at for d in sim.deliveries]
    assert times == sorted(times)
    seen: dict[str, list[str]] = defaultdict(list)
    for name, p in postings(sim):
        seen[name].append(p.txn_id)
    for name, txn_ids in seen.items():
        code = member(name).code
        assert txn_ids == [f"{code}-{i:09d}" for i in range(1, len(txn_ids) + 1)]


def test_a_payment_between_two_accounts_is_a_debit_and_a_credit_with_the_same_payment(
    sim: Simulation,
) -> None:
    by_payment: dict[str, list[tuple[str, LedgerPosting]]] = defaultdict(list)
    for name, p in postings(sim):
        by_payment[p.payment.reference].append((name, p))
    for reference, legs in by_payment.items():
        if isinstance(legs[0][1].counterparty, ExitDetail):
            assert len(legs) == 1, reference
            assert legs[0][1].direction is Direction.DEBIT
            continue
        assert len(legs) == 2, reference
        (payer_member, debit), (payee_member, credit) = legs
        assert debit.direction is Direction.DEBIT
        assert credit.direction is Direction.CREDIT
        assert debit.payment == credit.payment
        assert isinstance(debit.counterparty, AccountRef)
        assert isinstance(credit.counterparty, AccountRef)
        assert debit.counterparty.account_number == credit.account_number
        assert credit.counterparty.account_number == debit.account_number
        assert (payer_member == payee_member) == (debit.payment.rail is Rail.INTERNAL)


def test_no_account_ever_goes_below_zero(sim: Simulation) -> None:
    balance: dict[tuple[str, str], int] = {}
    for d in sim.deliveries:
        m = d.message
        if isinstance(m, AccountOpening):
            balance[(d.member, m.account_number)] = m.opening_balance
            continue
        key = (d.member, m.account_number)
        balance[key] += m.payment.amount if m.direction is Direction.CREDIT else -m.payment.amount
        assert balance[key] >= 0, key


def test_every_identifier_belongs_to_its_institution(sim: Simulation) -> None:
    numbers: set[str] = set()
    for d in sim.deliveries:
        m = d.message
        if isinstance(m, AccountOpening):
            assert m.ifsc.startswith(member(d.member).code)
            if m.vpa:
                assert m.vpa.endswith("@" + member(d.member).upi_handle)
            assert m.account_number not in numbers
            numbers.add(m.account_number)
        elif m.payment.rail in (Rail.NEFT, Rail.RTGS) and m.direction is Direction.DEBIT:
            assert m.payment.reference.startswith(member(d.member).code)


def test_the_month_has_every_rail_and_exit(sim: Simulation) -> None:
    rails = Counter(p.payment.rail for _, p in postings(sim))
    exits = Counter(p.counterparty.mode for _, p in postings(sim) if isinstance(p.counterparty, ExitDetail))
    assert set(rails) == set(Rail)
    assert set(exits) == {ExitMode.ATM, ExitMode.POS, ExitMode.CRYPTO}
    assert {d.member for d in sim.deliveries} == {m.name for m in NETWORK}


def test_traffic_stays_in_the_month(sim: Simulation) -> None:
    days = set(month_days(MONTH))
    for _, p in postings(sim):
        assert p.payment.at.astimezone(sim.story.reported_at.tzinfo).date() in days


def test_salary_arrives_once_and_rent_is_paid_once(sim: Simulation) -> None:
    pop = sim.population
    employers = {e.number for e in pop.employers}
    salary_credits: Counter[str] = Counter()
    rents: Counter[str] = Counter()
    landlords = {t: landlord.number for t, (landlord, _) in pop.landlord_of.items()}
    for _, p in postings(sim):
        cp = p.counterparty
        if not isinstance(cp, AccountRef):
            continue
        if p.direction is Direction.CREDIT and cp.account_number in employers:
            salary_credits[p.account_number] += 1
        if p.direction is Direction.DEBIT and landlords.get(p.account_number) == cp.account_number:
            rents[p.account_number] += 1
    assert salary_credits == Counter({p.number: 1 for p in pop.people})
    assert all(n <= 1 for n in rents.values())
    assert len(rents) > len(landlords) * 0.8  # a few tenants may be short of money that day


def test_story_accounts_take_no_part_in_ordinary_traffic(sim: Simulation) -> None:
    story = {a.number for a in sim.story.accounts.values()}
    story_refs = {s.payment.reference for s in sim.story.steps}
    for _, p in postings(sim):
        if p.account_number in story:
            assert p.payment.reference in story_refs
