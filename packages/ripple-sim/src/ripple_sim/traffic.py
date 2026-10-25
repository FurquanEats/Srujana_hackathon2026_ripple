"""A month of ordinary Indian bank traffic, so the demo's scam is a few payments among thousands.

Who is in it: salaried people and their employers, shops and their suppliers, landlords and tenants, an
electricity board, and a few people who also keep a wallet or a crypto exchange account. What they do:

- salaries by NEFT on each employer's payday, between the 1st and the 7th (or an internal transfer when employer
  and employee share a bank)
- rent by UPI between the 1st and the 5th
- UPI purchases at shops most days, and UPI transfers between people
- shops paying suppliers weekly by NEFT or RTGS
- electricity bills in the second week
- cash at ATMs and debit card payments at shops, which leave the banking system (exits)
- wallet top-ups and wallet spending, and exchange deposits followed by crypto withdrawals

The amounts and the mix follow published figures where one exists; the constants below name them, and
packages/ripple-sim/README.md cites each source and says which figures are our own assumptions.

A payment that the payer cannot afford at that moment is skipped, as a bank would decline it.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ripple_core.clock import IST
from ripple_core.messages import ExitMode, Rail
from ripple_core.money import rupees
from ripple_sim.events import DeclaredProfile, HolderKind
from ripple_sim.network import BANKS, member
from ripple_sim.world import Account, InsufficientFundsError, World

FIRST_NAMES = (
    "Aarti",
    "Abhishek",
    "Aditi",
    "Amit",
    "Anjali",
    "Arun",
    "Bhavna",
    "Deepak",
    "Divya",
    "Farhan",
    "Gaurav",
    "Geeta",
    "Harish",
    "Imran",
    "Jaya",
    "Karan",
    "Kavita",
    "Lakshmi",
    "Manoj",
    "Meena",
    "Mohan",
    "Nandini",
    "Neha",
    "Nikhil",
    "Pallavi",
    "Pradeep",
    "Priya",
    "Rahul",
    "Rekha",
    "Rohit",
    "Sameer",
    "Sangeeta",
    "Shalini",
    "Sunil",
    "Swati",
    "Tanvir",
    "Usha",
    "Varun",
    "Vinod",
    "Zoya",
)
SURNAMES = (
    "Agarwal",
    "Banerjee",
    "Chauhan",
    "Das",
    "Deshpande",
    "Fernandes",
    "Gupta",
    "Iyer",
    "Jain",
    "Khan",
    "Kulkarni",
    "Menon",
    "Mishra",
    "Nair",
    "Patel",
    "Pillai",
    "Rao",
    "Reddy",
    "Saxena",
    "Sharma",
    "Singh",
    "Thakur",
    "Verma",
    "Yadav",
)
SHOP_KINDS = (
    ("Kirana Store", "Grocery retail", "60,00,000"),
    ("Medicals", "Pharmacy", "80,00,000"),
    ("Dhaba", "Restaurant", "40,00,000"),
    ("Fuel Station", "Fuel retail", "3,00,00,000"),
    ("Mobile Shop", "Mobile phone retail", "90,00,000"),
    ("Sweets", "Sweet shop", "35,00,000"),
)
EMPLOYERS = (
    ("Infotech Pvt Ltd", "Software services"),
    ("Logistics Pvt Ltd", "Logistics"),
    ("Textiles Ltd", "Textile manufacturing"),
    ("Hospital", "Healthcare"),
)
OCCUPATIONS = (
    ("Software engineer", "12,00,000"),
    ("Accountant", "6,00,000"),
    ("Nurse", "4,80,000"),
    ("Warehouse supervisor", "4,20,000"),
    ("Machine operator", "3,00,000"),
    ("Teacher", "5,40,000"),
)


# Published figures (sources in README.md, "Where the numbers come from").
P2M_UNDER_500 = 0.86  # share of UPI shop payments below Rs 500 (NPCI via PIB, FY 2025-26)
P2M_SPLIT_RUPEES = (
    20,
    500,
    12_000,
)  # log-uniform below and above Rs 500; mean about Rs 635 (published Rs 589)
P2P_UNDER_500 = 0.59  # share of UPI transfers between people below Rs 500 (same source)
P2P_SPLIT_RUPEES = (50, 500, 23_000)  # mean about Rs 2,500, as NPCI's February 2026 P2P value over volume
P2P_PER_P2M = 37 / 63  # UPI volume: 63% to merchants, 37% between people (FY 2025-26)
ATM_RUPEES = (500, 11_000)  # steps of Rs 500, mean Rs 5,750 (CMS Info Systems: Rs 5,835 average in 2025)
POS_RUPEES = (
    200,
    15_000,
)  # log-uniform, mean about Rs 3,430 (RBI: debit cards averaged about Rs 3,370 in 2025)
POS_PER_DAY = 0.01  # debit card payments are about 0.6% of UPI volume (RBI Payment System Report, CY 2025)
LAST_PAYDAY = 7  # monthly wages are due before the 7th day of the next month ends (Code on Wages, s.17(1))

# Our own assumptions: no public per-person figure exists for these.
SHOP_PAYMENTS_PER_DAY = ((0, 1, 2, 3), (35, 35, 20, 10))  # about 1.05 UPI shop payments per person per day
ATM_PER_DAY = 0.03  # about one ATM visit a month


@dataclass(frozen=True)
class TrafficConfig:
    month: date  # any day in the month; traffic runs from its 1st to its last day
    people_per_bank: int = 60
    shops_per_bank: int = 6
    employers_per_bank: int = 1


@dataclass
class Population:
    people: list[Account]
    employers: list[Account]
    shops: list[Account]
    suppliers: list[Account]
    electricity_board: Account
    employer_of: dict[str, Account]  # person's account number -> employer
    salary: dict[str, int]  # person's account number -> monthly net salary
    landlord_of: dict[str, tuple[Account, int]]  # tenant's account number -> (landlord, rent)
    wallet_of: dict[str, Account]
    exchange_of: dict[str, Account]
    merchant_ids: dict[str, str]  # shop account number -> merchant ID for card payments


def month_days(month: date) -> list[date]:
    first = month.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return [first + timedelta(days=i) for i in range((nxt - first).days)]


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"


def build_population(world: World, rng: random.Random, config: TrafficConfig) -> Population:
    opened = datetime.combine(month_days(config.month)[0] - timedelta(days=400), time(10, 30), IST)
    people: list[Account] = []
    employers: list[Account] = []
    shops: list[Account] = []
    suppliers: list[Account] = []
    for bank in BANKS:
        for i in range(config.employers_per_bank):
            title, sector = EMPLOYERS[(BANKS.index(bank) + i) % len(EMPLOYERS)]
            employers.append(
                world.open(
                    bank,
                    f"{rng.choice(SURNAMES)} {title}",
                    DeclaredProfile(
                        holder_kind=HolderKind.BUSINESS,
                        occupation=sector,
                        annual_income=rupees("40,00,00,000"),
                        business_type="private limited company",
                    ),
                    rupees("2,50,00,000"),
                    opened,
                    branch=1,
                    upi=False,
                )
            )
        for _ in range(config.shops_per_bank):
            title, sector, turnover = rng.choice(SHOP_KINDS)
            shops.append(
                world.open(
                    bank,
                    f"{rng.choice(SURNAMES)} {title}",
                    DeclaredProfile(
                        holder_kind=HolderKind.BUSINESS,
                        occupation=sector,
                        annual_income=rupees(turnover),
                        business_type="proprietorship",
                    ),
                    rupees(rng.randrange(80_000, 6_00_000)),
                    opened,
                    branch=rng.randrange(3),
                )
            )
        suppliers.append(
            world.open(
                bank,
                f"{rng.choice(SURNAMES)} Wholesale Traders",
                DeclaredProfile(
                    holder_kind=HolderKind.BUSINESS,
                    occupation="Wholesale distribution",
                    annual_income=rupees("12,00,00,000"),
                    business_type="partnership firm",
                ),
                rupees("40,00,000"),
                opened,
                branch=1,
            )
        )
        for _ in range(config.people_per_bank):
            occupation, income = rng.choice(OCCUPATIONS)
            people.append(
                world.open(
                    bank,
                    _name(rng),
                    DeclaredProfile(
                        holder_kind=HolderKind.INDIVIDUAL, occupation=occupation, annual_income=rupees(income)
                    ),
                    rupees(rng.randrange(3_000, 2_50_000)),
                    opened,
                    branch=rng.randrange(3),
                )
            )
    board = world.open(
        BANKS[0],
        "State Electricity Distribution Co",
        DeclaredProfile(
            holder_kind=HolderKind.BUSINESS,
            occupation="Electricity distribution",
            annual_income=rupees("900,00,00,000"),
            business_type="state undertaking",
        ),
        rupees("5,00,00,000"),
        opened,
        branch=2,
    )

    employer_of: dict[str, Account] = {}
    salary: dict[str, int] = {}
    for p in people:
        employer_of[p.number] = rng.choice(employers)
        yearly = p.profile.annual_income
        salary[p.number] = (
            (yearly // 12 * rng.randrange(78, 92) // 100) // 100 * 100
        )  # net of PF and tax, whole rupees

    landlord_of: dict[str, tuple[Account, int]] = {}
    shuffled = people[:]
    rng.shuffle(shuffled)
    landlords, tenants = shuffled[: len(people) // 6], shuffled[len(people) // 6 : len(people) // 2]
    for tenant in tenants:
        landlord_of[tenant.number] = (rng.choice(landlords), rupees(rng.randrange(6_000, 32_000, 500)))

    wallet_member, exchange_member = member("wallet-w"), member("exchange-x")
    wallet_of = {
        p.number: world.open(wallet_member, p.holder, p.profile, 0, opened)
        for p in rng.sample(people, len(people) // 5)
    }
    exchange_of = {
        p.number: world.open(exchange_member, p.holder, p.profile, 0, opened, upi=False)
        for p in rng.sample(people, len(people) // 25)
    }
    merchant_ids = {s.number: world.ids.merchant_id() for s in shops}
    return Population(
        people,
        employers,
        shops,
        suppliers,
        board,
        employer_of,
        salary,
        landlord_of,
        wallet_of,
        exchange_of,
        merchant_ids,
    )


@dataclass(frozen=True)
class Intent:
    at: datetime
    seq: int
    run: Callable[[datetime], object]


def _at(day: date, rng: random.Random, start: int = 7, end: int = 23) -> datetime:
    minute = rng.randrange(start * 60, end * 60)
    return datetime.combine(day, time(minute // 60, minute % 60), IST)


def _amount(rng: random.Random, low: int, high: int, step: int = 1) -> int:
    """A rupee amount between `low` and `high`, in paise."""
    return rupees(rng.randrange(low, high + 1, step))


def _log_uniform(rng: random.Random, low: int, high: int) -> int:
    """A whole-rupee amount between `low` and `high`, spread evenly on a log scale (many small, few large), in paise."""
    return rupees(round(math.exp(rng.uniform(math.log(low), math.log(high)))))


def _split(rng: random.Random, under_share: float, bounds: tuple[int, int, int]) -> int:
    """A UPI amount: below the middle bound with probability `under_share`, otherwise above it, in paise."""
    low, middle, high = bounds
    if rng.random() < under_share:
        return _log_uniform(rng, low, middle - 1)
    return _log_uniform(rng, middle, high)


def _count(rng: random.Random, mean: float) -> int:
    """How many times something happens in a day, for a daily mean below 3."""
    whole, part = divmod(mean, 1)
    return int(whole) + (rng.random() < part)


def plan_month(world: World, rng: random.Random, pop: Population, config: TrafficConfig) -> list[Intent]:  # noqa: PLR0912
    intents: list[Intent] = []

    def add(at: datetime, run: Callable[[datetime], object]) -> None:
        intents.append(Intent(at, len(intents), run))

    def pay(
        payer: Account, payee: Account, amount: int, rail: Rail | None = None
    ) -> Callable[[datetime], object]:
        return lambda at: world.pay(payer, payee, amount, at, rail)

    def exit_(
        account: Account, amount: int, mode: ExitMode, ident: str, where: str | None
    ) -> Callable[[datetime], object]:
        return lambda at: world.exit(account, amount, at, mode=mode, identifier=ident, location=where)

    atm_ids = {b.code: [world.ids.atm_id(b.code) for _ in range(4)] for b in BANKS}
    payday = {e.number: rng.randint(1, LAST_PAYDAY) for e in pop.employers}
    p2p_per_day = sum(n * w for n, w in zip(*SHOP_PAYMENTS_PER_DAY, strict=True)) / 100 * P2P_PER_P2M

    for day in month_days(config.month):
        for p in pop.people:
            employer = pop.employer_of[p.number]
            if day.day == payday[employer.number]:
                add(_at(day, rng, 9, 11), pay(employer, p, pop.salary[p.number], Rail.NEFT))
        if day.day == 1:
            for tenant in pop.people:  # rent once a month, on a day between the 1st and the 5th
                if tenant.number in pop.landlord_of:
                    landlord, rent = pop.landlord_of[tenant.number]
                    add(
                        _at(day + timedelta(days=rng.randrange(5)), rng),
                        pay(tenant, landlord, rent, Rail.UPI),
                    )
        if day.day == 8:  # most people pay the electricity bill once, in the second week
            for p in pop.people:
                if rng.random() < 0.9:
                    when = _at(day + timedelta(days=rng.randrange(7)), rng, 9, 22)
                    add(when, pay(p, pop.electricity_board, _amount(rng, 400, 4_500, 10), Rail.UPI))
        if day.weekday() == 0:
            for shop in pop.shops:
                supplier = rng.choice(pop.suppliers)
                amount = _amount(rng, 20_000, 2_80_000, 100)
                add(
                    _at(day, rng, 10, 17),
                    pay(shop, supplier, amount, Rail.RTGS if amount >= 2_00_000_00 else Rail.NEFT),
                )

        for p in pop.people:
            for _ in range(rng.choices(*SHOP_PAYMENTS_PER_DAY)[0]):
                shop = rng.choice(pop.shops)
                add(_at(day, rng), pay(p, shop, _split(rng, P2M_UNDER_500, P2M_SPLIT_RUPEES), Rail.UPI))
            for _ in range(_count(rng, p2p_per_day)):
                friend = rng.choice([q for q in pop.people if q is not p])
                add(_at(day, rng), pay(p, friend, _split(rng, P2P_UNDER_500, P2P_SPLIT_RUPEES), Rail.UPI))
            if rng.random() < ATM_PER_DAY:
                atm = rng.choice(atm_ids[p.member.code])
                add(
                    _at(day, rng, 6, 23),
                    exit_(p, _amount(rng, *ATM_RUPEES, 500), ExitMode.ATM, atm, p.member.city),
                )
            if rng.random() < POS_PER_DAY:
                shop = rng.choice(pop.shops)
                add(
                    _at(day, rng, 10, 22),
                    exit_(
                        p,
                        _log_uniform(rng, *POS_RUPEES),
                        ExitMode.POS,
                        pop.merchant_ids[shop.number],
                        shop.member.city,
                    ),
                )
            wallet = pop.wallet_of.get(p.number)
            if wallet is not None and rng.random() < 0.05:
                load = _amount(rng, 500, 5_000, 100)
                add(_at(day, rng), pay(p, wallet, load, Rail.UPI))
                add(
                    _at(day, rng, 21, 23), pay(wallet, rng.choice(pop.shops), _amount(rng, 50, 400), Rail.UPI)
                )
            exchange = pop.exchange_of.get(p.number)
            if exchange is not None and rng.random() < 0.03:
                deposit = _amount(rng, 2_000, 50_000, 1_000)
                add(_at(day, rng, 9, 18), pay(p, exchange, deposit, Rail.IMPS))
                add(
                    _at(day, rng, 19, 23),
                    exit_(exchange, deposit, ExitMode.CRYPTO, world.ids.crypto_address(), None),
                )
    return intents


def run_month(world: World, rng: random.Random, config: TrafficConfig) -> tuple[Population, int, int]:
    """Plan and post the month. Returns the population and how many intents were posted and skipped."""
    pop = build_population(world, rng, config)
    intents = sorted(plan_month(world, rng, pop, config), key=lambda i: (i.at, i.seq))
    posted = skipped = 0
    for intent in intents:
        try:
            intent.run(intent.at)
        except InsufficientFundsError:
            skipped += 1
        else:
            posted += 1
    return pop, posted, skipped
