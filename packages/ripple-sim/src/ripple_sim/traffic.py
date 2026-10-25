"""A month of ordinary Indian bank traffic, so the demo's scam is a few payments among thousands.

Who is in it: salaried people and their employers, shops and their suppliers, landlords and tenants, an
electricity board, and a few people who also keep a wallet or a crypto exchange account. What they do:

- salaries by NEFT on the 1st (or an internal transfer when employer and employee share a bank)
- rent by UPI between the 1st and the 5th
- UPI purchases at shops most days, and UPI transfers between people
- shops paying suppliers weekly by NEFT or RTGS
- electricity bills in the second week
- cash at ATMs and card payments at shops, which leave the banking system (exits)
- wallet top-ups and wallet spending, and exchange deposits followed by crypto withdrawals

A payment that the payer cannot afford at that moment is skipped, as a bank would decline it.
"""

from __future__ import annotations

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

    for day in month_days(config.month):
        if day.day == 1:
            for p in pop.people:
                employer = pop.employer_of[p.number]
                add(_at(day, rng, 9, 11), pay(employer, p, pop.salary[p.number], Rail.NEFT))
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
            for _ in range(rng.choices((0, 1, 2, 3), (35, 35, 20, 10))[0]):
                add(_at(day, rng), pay(p, rng.choice(pop.shops), _amount(rng, 30, 2_500), Rail.UPI))
            roll = rng.random()
            if roll < 0.04:
                add(_at(day, rng), pay(p, rng.choice(pop.people), _amount(rng, 100, 8_000, 50), Rail.UPI))
            elif roll < 0.07:
                atm = rng.choice(atm_ids[p.member.code])
                add(
                    _at(day, rng, 6, 23),
                    exit_(p, _amount(rng, 500, 10_000, 500), ExitMode.ATM, atm, p.member.city),
                )
            elif roll < 0.10:
                shop = rng.choice(pop.shops)
                add(
                    _at(day, rng, 10, 22),
                    exit_(
                        p,
                        _amount(rng, 200, 15_000),
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
