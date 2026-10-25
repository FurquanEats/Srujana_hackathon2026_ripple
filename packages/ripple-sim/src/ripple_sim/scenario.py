"""The PRD's demo story as a fixed scenario, with its exact amounts.

A victim at Bank A is coached into sending Rs 8,00,000 by RTGS to a first mule, M1, at Bank B. M1 keeps
Rs 1,00,000 and sends Rs 3,00,000 to M2 at Bank C, Rs 2,50,000 to M3 at Bank D and Rs 1,50,000 to a wallet at
Wallet W. M2 takes Rs 2,00,000 in cash at two ATMs and sends Rs 1,00,000 to Exchange X. M3 already holds
Rs 3,00,000 of its own money, and pays Ravi Traders Rs 2,00,000, Galaxy Mobiles Rs 1,20,000 and a shop assistant's
Rs 15,000 salary.

Under the SOP's rule (victims' money leaves before the holder's own), Ravi Traders carries Rs 2,00,000 of traced
money, Galaxy Mobiles Rs 50,000 and the salary Rs 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ripple_core import ids
from ripple_core.clock import IST
from ripple_core.messages import ExitMode, Payment, Rail
from ripple_core.money import rupees
from ripple_sim.events import DeclaredProfile, HolderKind
from ripple_sim.network import member
from ripple_sim.world import Account, World

# Small balances the mules hold before the scam, so their own money is visible but never confused with the
# victim's. M3's own money is the PRD's Rs 3,00,000.
M1_OWN = rupees("1,240")
M2_OWN = rupees(860)
M3_OWN = rupees("3,00,000")


@dataclass(frozen=True)
class Step:
    name: str
    payer: str  # role
    payee: str | None  # role, or None for an exit
    payment: Payment
    exit_identifier: str | None = None


@dataclass(frozen=True)
class DemoStory:
    ack_number: str  # the victim's 1930 complaint
    reported_at: datetime
    accounts: dict[str, Account]  # role -> account
    steps: tuple[Step, ...]

    def step(self, name: str) -> Step:
        return next(s for s in self.steps if s.name == name)


def _individual(occupation: str, income: str) -> DeclaredProfile:
    return DeclaredProfile(
        holder_kind=HolderKind.INDIVIDUAL, occupation=occupation, annual_income=rupees(income)
    )


def _business(occupation: str, turnover: str, business_type: str = "proprietorship") -> DeclaredProfile:
    return DeclaredProfile(
        holder_kind=HolderKind.BUSINESS,
        occupation=occupation,
        annual_income=rupees(turnover),
        business_type=business_type,
    )


def open_story_accounts(world: World, opened_at: datetime) -> dict[str, Account]:
    """Open the story's accounts. They take no part in ordinary traffic, so their ledgers stay readable."""
    a, b, c, d = (member(n) for n in ("bank-a", "bank-b", "bank-c", "bank-d"))
    w, x = member("wallet-w"), member("exchange-x")
    tag = frozenset({"story"})
    return {
        "victim": world.open(
            a,
            "Sudha Raman",
            _individual("Retired bank officer", "9,60,000"),
            rupees("14,25,000"),
            opened_at,
            tags=tag,
        ),
        "m1": world.open(
            b, "Arjun Mondal", _individual("Student", "0"), M1_OWN, opened_at, tags=tag | {"mule"}
        ),
        "m2": world.open(
            c,
            "Bikash Shaw",
            _individual("Delivery rider", "1,80,000"),
            M2_OWN,
            opened_at,
            tags=tag | {"mule"},
        ),
        "m3": world.open(
            d,
            "Sagar Mobile Point",
            _business("Mobile accessories retail", "45,00,000"),
            M3_OWN,
            opened_at,
            tags=tag | {"mule"},
        ),
        "m1_wallet": world.open(
            w, "Arjun Mondal", _individual("Student", "0"), 0, opened_at, tags=tag | {"mule"}
        ),
        "m2_exchange": world.open(
            x, "Bikash Shaw", _individual("Delivery rider", "1,80,000"), 0, opened_at, tags=tag | {"mule"}
        ),
        "ravi_traders": world.open(
            a,
            "Ravi Traders",
            _business("Electronics wholesale", "3,20,00,000"),
            rupees("6,40,000"),
            opened_at,
            tags=tag,
        ),
        "galaxy_mobiles": world.open(
            b,
            "Galaxy Mobiles",
            _business("Mobile phone retail", "1,10,00,000"),
            rupees("2,15,000"),
            opened_at,
            tags=tag,
        ),
        "shop_assistant": world.open(
            c, "Pooja Das", _individual("Shop assistant", "1,80,000"), rupees("4,300"), opened_at, tags=tag
        ),
    }


def play_demo_story(world: World, accounts: dict[str, Account], start: datetime) -> DemoStory:
    """Post the story's payments, starting at `start` (the victim's RTGS)."""
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")
    t = start.astimezone(IST)
    acc = accounts
    steps: list[Step] = []

    def pay(name: str, payer: str, payee: str, amount: str, minutes: int, *, rail: Rail) -> None:
        payment = world.pay(acc[payer], acc[payee], rupees(amount), t + timedelta(minutes=minutes), rail)
        steps.append(Step(name, payer, payee, payment))

    def atm(name: str, payer: str, amount: str, minutes: int, location: str) -> None:
        atm_id = world.ids.atm_id(acc[payer].member.code)
        payment = world.exit(
            acc[payer],
            rupees(amount),
            t + timedelta(minutes=minutes),
            mode=ExitMode.ATM,
            identifier=atm_id,
            location=location,
        )
        steps.append(Step(name, payer, None, payment, atm_id))

    pay("victim_to_m1", "victim", "m1", "8,00,000", 0, rail=Rail.RTGS)
    pay("m1_to_m2", "m1", "m2", "3,00,000", 7, rail=Rail.IMPS)
    pay("m1_to_m3", "m1", "m3", "2,50,000", 9, rail=Rail.RTGS)
    pay("m1_to_wallet", "m1", "m1_wallet", "1,50,000", 12, rail=Rail.IMPS)
    pay("m2_to_exchange", "m2", "m2_exchange", "1,00,000", 26, rail=Rail.IMPS)
    atm("m2_atm_1", "m2", "1,00,000", 38, "Howrah Maidan, Kolkata")
    atm("m2_atm_2", "m2", "1,00,000", 51, "Shibpur, Howrah")
    pay("m3_to_ravi_traders", "m3", "ravi_traders", "2,00,000", 64, rail=Rail.NEFT)
    pay("m3_to_galaxy_mobiles", "m3", "galaxy_mobiles", "1,20,000", 71, rail=Rail.IMPS)
    pay("m3_salary", "m3", "shop_assistant", "15,000", 83, rail=Rail.UPI)

    return DemoStory(
        ack_number=world.ids.ack_number(ids.ComplaintChannel.HELPLINE_1930),
        reported_at=(t + timedelta(minutes=95)),
        accounts=acc,
        steps=tuple(steps),
    )
