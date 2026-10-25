from collections.abc import Mapping

import pytest

from ripple_core import ids
from ripple_core.messages import AccountOpening, ExitMode, LedgerPosting, Rail
from ripple_core.money import rupees
from ripple_core.tracing import AccountTrace, Direction, Entry, trace_account
from ripple_sim.cli import EXPECTED_TRACED
from ripple_sim.scenario import M1_OWN, M2_OWN, M3_OWN
from ripple_sim.simulation import DEFAULT_MONTH, Simulation, simulate
from ripple_sim.traffic import TrafficConfig


@pytest.fixture(scope="module")
def sim() -> Simulation:
    return simulate(seed=11, config=TrafficConfig(month=DEFAULT_MONTH, people_per_bank=15, shops_per_bank=3))


def ledger(sim: Simulation, role: str) -> tuple[int, list[LedgerPosting]]:
    """The opening balance and postings of one story account, from what its own institution received."""
    account = sim.story.accounts[role]
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


def trace(sim: Simulation, role: str, traced_in: Mapping[str, int]) -> tuple[AccountTrace, dict[str, str]]:
    """Trace one claim through a story account. `traced_in` maps a payment reference to the claim's paise in it."""
    opening, postings = ledger(sim, role)
    entries = [Entry(p.txn_id, p.payment.at, Direction(p.direction), p.payment.amount) for p in postings]
    by_ref = {p.payment.reference: p.txn_id for p in postings}
    claim = sim.story.ack_number
    result = trace_account(
        entries,
        opening_balance=opening,
        traced_in={by_ref[ref]: {claim: paise} for ref, paise in traced_in.items()},
    )
    return result, {p.txn_id: p.payment.reference for p in postings}


def carried(result: AccountTrace, refs: dict[str, str], sim: Simulation, step: str) -> int:
    reference = sim.story.step(step).payment.reference
    return next(d.traced for d in result.debits if refs[d.txn_id] == reference)


def test_the_story_has_the_prds_amounts_and_rails(sim: Simulation) -> None:
    expected = {
        "victim_to_m1": ("8,00,000", Rail.RTGS),
        "m1_to_m2": ("3,00,000", Rail.IMPS),
        "m1_to_m3": ("2,50,000", Rail.RTGS),
        "m1_to_wallet": ("1,50,000", Rail.IMPS),
        "m2_to_exchange": ("1,00,000", Rail.IMPS),
        "m2_atm_1": ("1,00,000", Rail.INTERNAL),
        "m2_atm_2": ("1,00,000", Rail.INTERNAL),
        "m3_to_ravi_traders": ("2,00,000", Rail.NEFT),
        "m3_to_galaxy_mobiles": ("1,20,000", Rail.IMPS),
        "m3_salary": ("15,000", Rail.UPI),
    }
    assert [s.name for s in sim.story.steps] == list(expected)
    for name, (amount, rail) in expected.items():
        step = sim.story.step(name)
        assert step.payment.amount == rupees(amount), name
        assert step.payment.rail is rail, name
    times = [s.payment.at for s in sim.story.steps]
    assert times == sorted(times)
    assert ids.complaint_channel(sim.story.ack_number) is ids.ComplaintChannel.HELPLINE_1930


def test_each_account_sits_at_the_prds_institution(sim: Simulation) -> None:
    where = {role: a.member.id for role, a in sim.story.accounts.items()}
    assert where["victim"] == "bank-a"
    assert where["m1"] == "bank-b"
    assert where["m2"] == "bank-c"
    assert where["m3"] == "bank-d"
    assert where["m1_wallet"] == "wallet-w"
    assert where["m2_exchange"] == "exchange-x"
    for a in sim.story.accounts.values():
        assert a.ifsc.startswith(a.member.code)


def test_m1_keeps_one_lakh_of_the_victims_money(sim: Simulation) -> None:
    victim_rtgs = sim.story.step("victim_to_m1").payment
    result, refs = trace(sim, "m1", {victim_rtgs.reference: victim_rtgs.amount})
    assert result.traced_remaining == rupees("1,00,000")
    assert result.own == M1_OWN
    for step in ("m1_to_m2", "m1_to_m3", "m1_to_wallet"):
        assert carried(result, refs, sim, step) == sim.story.step(step).payment.amount


def test_m2_passes_on_or_cashes_out_everything(sim: Simulation) -> None:
    in_ = sim.story.step("m1_to_m2").payment
    result, refs = trace(sim, "m2", {in_.reference: in_.amount})
    assert result.traced_remaining == 0
    assert result.own == M2_OWN
    for step in ("m2_to_exchange", "m2_atm_1", "m2_atm_2"):
        assert carried(result, refs, sim, step) == rupees("1,00,000")


def test_m3_traces_ravi_traders_galaxy_mobiles_and_the_salary_as_the_prd_says(sim: Simulation) -> None:
    in_ = sim.story.step("m1_to_m3").payment
    result, refs = trace(sim, "m3", {in_.reference: in_.amount})
    for step, amount in EXPECTED_TRACED.items():
        assert carried(result, refs, sim, step) == amount, step
    assert result.traced_remaining == 0
    assert result.own == M3_OWN + rupees("2,50,000") - rupees("3,35,000") - 0


def test_atm_exits_carry_an_atm_id_and_location(sim: Simulation) -> None:
    _, postings = ledger(sim, "m2")
    exits = [p.exit for p in postings if p.exit is not None]
    assert len(exits) == 2
    assert all(e.mode is ExitMode.ATM and e.identifier.startswith("BKCC") and e.location for e in exits)
    assert len({e.identifier for e in exits}) == 2  # two different ATMs


def test_interbank_story_payments_reach_both_ledgers(sim: Simulation) -> None:
    step = sim.story.step("victim_to_m1")
    at_a = [d.message for d in sim.for_member("bank-a") if isinstance(d.message, LedgerPosting)]
    at_b = [d.message for d in sim.for_member("bank-b") if isinstance(d.message, LedgerPosting)]
    debit = [p for p in at_a if p.payment == step.payment]
    credit = [p for p in at_b if p.payment == step.payment]
    assert [p.direction for p in debit] == [Direction.DEBIT]
    assert [p.direction for p in credit] == [Direction.CREDIT]
    assert debit[0].account_number == sim.story.accounts["victim"].number
    assert credit[0].account_number == sim.story.accounts["m1"].number
