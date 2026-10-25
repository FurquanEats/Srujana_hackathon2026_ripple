"""Three more scam shapes beside the digital-arrest story, so detection is not tuned to one pattern.

- **Investment scam.** A retired engineer is added to a "stock tips" WhatsApp group and pays a fake trading app
  in 14 UPI transfers over four days, each under UPI's Rs 1 lakh cap. Two first-layer mules each forward 98% of
  every credit within the hour to a collector, keeping 2% as commission. Each evening the collector moves the
  day's money to its crypto exchange account, which withdraws it as crypto that night. On the fourth evening the
  victim is asked for a "withdrawal fee", refuses and reports the next morning, before that day's crypto
  withdrawal: that day's money is still at the exchange.
- **Patient mule.** A fake courier-customs call: the victim pays Rs 3,40,000 by IMPS late in the evening. The mule
  waits nine hours before moving anything, so rules that look for money leaving within minutes miss it. It then
  sends Rs 1,90,000 to a second mule and takes cash in Rs 10,000 withdrawals; the second mule waits six more
  hours, takes cash and loads its wallet. The victim reports the next afternoon.
- **Task scam.** Four people answer a "part-time job: like videos, earn daily" message and pay escalating "task
  deposits" by UPI into one mule, a small shop's current account with its own takings. Their money mixes with
  the shop's and with each other's, and the mule forwards round sums to a second mule who takes cash. Each victim
  files a separate complaint, so a hold there is shared among victims pro rata (SOP Annexure V, illustration 2).

All amounts and times are fixed, so a seed changes only the identifiers. Every scam runs inside the simulated
month, and its accounts take no part in ordinary traffic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from ripple_core import ids
from ripple_core.clock import IST
from ripple_core.messages import ExitMode, Rail
from ripple_core.money import rupees
from ripple_sim.events import DeclaredProfile, HolderKind
from ripple_sim.network import member
from ripple_sim.scenario import Step
from ripple_sim.world import Account, World

FIRST_LAYER_KEEPS = 0.02  # the investment scam's mules keep 2% of each credit as commission


@dataclass(frozen=True)
class Report:
    """One victim's complaint to 1930 or NCRP, naming the payments they made."""

    ack_number: str
    victim: str  # role
    steps: tuple[str, ...]
    reported_at: datetime


@dataclass(frozen=True)
class Scam:
    name: str
    accounts: dict[str, Account]
    steps: tuple[Step, ...]
    reports: tuple[Report, ...]

    def step(self, name: str) -> Step:
        return next(s for s in self.steps if s.name == name)


def _individual(occupation: str, income: str) -> DeclaredProfile:
    return DeclaredProfile(
        holder_kind=HolderKind.INDIVIDUAL, occupation=occupation, annual_income=rupees(income)
    )


@dataclass
class _Play:
    """Builds one scam's steps and keeps their names unique and in time order."""

    world: World
    accounts: dict[str, Account]
    steps: list[Step] = field(default_factory=list)

    def pay(self, name: str, payer: str, payee: str, amount: int, at: datetime, *, rail: Rail) -> int:
        payment = self.world.pay(self.accounts[payer], self.accounts[payee], amount, at, rail)
        self.steps.append(Step(name, payer, payee, payment))
        return amount

    def cash(self, name: str, payer: str, amount: int, at: datetime, location: str) -> None:
        atm_id = self.world.ids.atm_id(self.accounts[payer].member.code)
        payment = self.world.exit(
            self.accounts[payer], amount, at, mode=ExitMode.ATM, identifier=atm_id, location=location
        )
        self.steps.append(Step(name, payer, None, payment, atm_id))

    def crypto(self, name: str, payer: str, amount: int, at: datetime) -> None:
        wallet = self.world.ids.crypto_address()
        payment = self.world.exit(self.accounts[payer], amount, at, mode=ExitMode.CRYPTO, identifier=wallet)
        self.steps.append(Step(name, payer, None, payment, wallet))

    def done(self, name: str, reports: tuple[Report, ...]) -> Scam:
        ordered = tuple(sorted(self.steps, key=lambda s: s.payment.at))
        return Scam(name, self.accounts, ordered, reports)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), IST)


def investment_scam(world: World, start: date, opened_at: datetime) -> Scam:
    """Fourteen UPI transfers over four days, through two mules and a collector into crypto (starts on `start`)."""
    tag = frozenset({"scam", "investment"})
    a, b, c, d, x = (member(n) for n in ("bank-a", "bank-b", "bank-c", "bank-d", "exchange-x"))
    firm = DeclaredProfile(
        holder_kind=HolderKind.BUSINESS,
        occupation="Financial consultancy",
        annual_income=rupees("12,00,000"),
        business_type="proprietorship",
    )
    acc = {
        "victim": world.open(
            c,
            "Rakesh Kulkarni",
            _individual("Retired engineer", "7,20,000"),
            rupees("18,40,000"),
            opened_at,
            tags=tag,
        ),
        "mule_a": world.open(a, "Rohan Verma", _individual("Student", "0"), rupees(650), opened_at, tags=tag),
        "mule_b": world.open(
            d, "Sunita Yadav", _individual("Homemaker", "0"), rupees("1,120"), opened_at, tags=tag
        ),
        "collector": world.open(
            b, "Vertex Capital Advisors", firm, rupees("8,400"), opened_at, upi=False, tags=tag
        ),
        "exchange": world.open(x, "Vertex Capital Advisors", firm, 0, opened_at, upi=False, tags=tag),
    }
    play = _Play(world, acc)
    # Four days, starting small and growing as the fake app shows "profits".
    days = [
        [("10:12", "25,000"), ("15:40", "50,000")],
        [("10:05", "60,000"), ("11:30", "99,000"), ("14:15", "99,000")],
        [("09:50", "99,000"), ("10:40", "99,000"), ("12:05", "99,000"), ("15:20", "95,000")],
        [
            ("10:00", "99,000"),
            ("10:55", "99,000"),
            ("11:45", "99,000"),
            ("13:10", "99,000"),
            ("16:30", "85,000"),
        ],
    ]
    victim_steps: list[str] = []
    n = 0
    for offset, payments in enumerate(days):
        day = start + timedelta(days=offset)
        collected = 0
        for clock, amount in payments:
            n += 1
            hour, minute = (int(v) for v in clock.split(":"))
            mule = "mule_a" if n % 2 else "mule_b"
            paid = _at(day, hour, minute)
            victim_steps.append(f"victim_upi_{n:02d}")
            play.pay(victim_steps[-1], "victim", mule, rupees(amount), paid, rail=Rail.UPI)
            kept = rupees(amount) * round(FIRST_LAYER_KEEPS * 100) // 100
            onward = (rupees(amount) - kept) // rupees(100) * rupees(100)  # whole hundreds of rupees
            collected += play.pay(
                f"{mule}_to_collector_{n:02d}",
                mule,
                "collector",
                onward,
                paid + timedelta(minutes=20 + 7 * (n % 4)),
                rail=Rail.IMPS,
            )
        play.pay(
            f"collector_to_exchange_day{offset + 1}",
            "collector",
            "exchange",
            collected,
            _at(day, 19, 30),
            rail=Rail.IMPS,
        )
        if offset < len(days) - 1:  # the last evening's money has not been withdrawn when the victim reports
            play.crypto(f"exchange_crypto_day{offset + 1}", "exchange", collected, _at(day, 22, 10))
    report = Report(
        world.ids.ack_number(ids.ComplaintChannel.NCRP),
        "victim",
        tuple(victim_steps),
        _at(start + timedelta(days=len(days)), 9, 40),
    )
    return play.done("investment", (report,))


def patient_mule(world: World, day: date, opened_at: datetime) -> Scam:
    """A mule that waits nine hours before moving the victim's money, then a second that waits six more."""
    tag = frozenset({"scam", "patient"})
    a, b, d, w = (member(n) for n in ("bank-a", "bank-b", "bank-d", "wallet-w"))
    acc = {
        "victim": world.open(
            d,
            "Ayesha Siddiqui",
            _individual("Schoolteacher", "6,60,000"),
            rupees("4,10,000"),
            opened_at,
            tags=tag,
        ),
        "mule": world.open(
            b, "Deepak Rathore", _individual("Driver", "2,40,000"), rupees("3,200"), opened_at, tags=tag
        ),
        "second": world.open(
            a, "Imran Sheikh", _individual("Labourer", "1,80,000"), rupees(900), opened_at, tags=tag
        ),
        "second_wallet": world.open(
            w, "Imran Sheikh", _individual("Labourer", "1,80,000"), 0, opened_at, tags=tag
        ),
    }
    play = _Play(world, acc)
    paid = _at(day, 19, 40)
    play.pay("victim_to_mule", "victim", "mule", rupees("3,40,000"), paid, rail=Rail.IMPS)
    moved = paid + timedelta(hours=9, minutes=15)  # 04:55 the next morning
    play.pay("mule_to_second", "mule", "second", rupees("1,90,000"), moved, rail=Rail.IMPS)
    for i in range(3):
        play.cash(
            f"mule_atm_{i + 1}",
            "mule",
            rupees("10,000"),
            moved + timedelta(minutes=35 + 6 * i),
            "Lal Darwaza, Ahmedabad",
        )
    later = moved + timedelta(hours=6)
    for i in range(5):
        play.cash(
            f"second_atm_{i + 1}",
            "second",
            rupees("10,000"),
            later + timedelta(minutes=5 * i),
            "Kurla West, Mumbai",
        )
    play.pay(
        "second_to_wallet",
        "second",
        "second_wallet",
        rupees("1,40,000"),
        later + timedelta(minutes=40),
        rail=Rail.IMPS,
    )
    report = Report(
        world.ids.ack_number(ids.ComplaintChannel.HELPLINE_1930),
        "victim",
        ("victim_to_mule",),
        paid + timedelta(hours=18, minutes=20),
    )
    return play.done("patient_mule", (report,))


def task_scam(world: World, start: date, opened_at: datetime) -> Scam:
    """Four victims' task deposits mix in one shop's account, then go on to a cash-out mule."""
    tag = frozenset({"scam", "task"})
    a, b, c, d = (member(n) for n in ("bank-a", "bank-b", "bank-c", "bank-d"))
    acc = {
        "victim_1": world.open(
            a, "Priya Nair", _individual("Nurse", "4,80,000"), rupees("1,35,000"), opened_at, tags=tag
        ),
        "victim_2": world.open(
            b, "Arjun Das", _individual("Accountant", "6,00,000"), rupees("92,000"), opened_at, tags=tag
        ),
        "victim_3": world.open(
            d, "Kavita Rao", _individual("Teacher", "5,40,000"), rupees("2,10,000"), opened_at, tags=tag
        ),
        "victim_4": world.open(
            a,
            "Manoj Gupta",
            _individual("Machine operator", "3,00,000"),
            rupees("48,000"),
            opened_at,
            tags=tag,
        ),
        "shop": world.open(
            c,
            "Shree Balaji Mobile Recharge",
            DeclaredProfile(
                holder_kind=HolderKind.BUSINESS,
                occupation="Mobile recharge and accessories",
                annual_income=rupees("9,00,000"),
                business_type="proprietorship",
            ),
            rupees("38,500"),
            opened_at,
            tags=tag,
        ),
        "cash_mule": world.open(
            d, "Sanjay Kumar", _individual("Unemployed", "0"), rupees(400), opened_at, tags=tag
        ),
        "customer": world.open(
            b, "Lakshmi Pillai", _individual("Tailor", "2,10,000"), rupees("26,000"), opened_at, tags=tag
        ),
    }
    play = _Play(world, acc)
    day1, day2 = start, start + timedelta(days=1)
    deposits = {
        "victim_1": [(day1, "11:05", "2,000"), (day1, "13:30", "9,000"), (day2, "10:20", "35,000")],
        "victim_2": [(day1, "12:10", "5,000"), (day1, "16:45", "28,000"), (day2, "12:40", "40,000")],
        "victim_3": [(day1, "14:00", "10,000"), (day2, "11:15", "60,000"), (day2, "15:30", "90,000")],
        "victim_4": [(day2, "09:45", "3,000"), (day2, "13:05", "22,000")],
    }
    reported: dict[str, list[str]] = {v: [] for v in deposits}
    for victim, rows in deposits.items():
        for i, (day, clock, amount) in enumerate(rows, 1):
            hour, minute = (int(v) for v in clock.split(":"))
            reported[victim].append(f"{victim}_task_{i}")
            play.pay(
                reported[victim][-1], victim, "shop", rupees(amount), _at(day, hour, minute), rail=Rail.UPI
            )
    # The shop keeps taking genuine recharge payments from a regular customer.
    for i, (day, hour, amount) in enumerate([(day1, 18, "1,200"), (day2, 9, "650"), (day2, 17, "2,400")], 1):
        play.pay(f"customer_{i}", "customer", "shop", rupees(amount), _at(day, hour, 30), rail=Rail.UPI)
    play.pay("shop_to_cash_mule_1", "shop", "cash_mule", rupees("50,000"), _at(day1, 17, 20), rail=Rail.IMPS)
    play.pay(
        "shop_to_cash_mule_2", "shop", "cash_mule", rupees("1,50,000"), _at(day2, 16, 10), rail=Rail.IMPS
    )
    for i, hour in enumerate((18, 19, 20, 21), 1):
        play.cash(f"cash_mule_atm_{i}", "cash_mule", rupees("20,000"), _at(day2, hour, 5), "Sector 18, Noida")
    reports = tuple(
        Report(
            world.ids.ack_number(ids.ComplaintChannel.NCRP),
            victim,
            tuple(steps),
            _at(start + timedelta(days=2), 10 + i, 0),
        )
        for i, (victim, steps) in enumerate(reported.items())
    )
    return play.done("task", reports)


def play_scams(world: World, month: date, opened_at: datetime) -> tuple[Scam, ...]:
    """The three scams, on days that keep each one, and its reports, inside the month."""
    first = month.replace(day=1)
    return (
        investment_scam(world, first + timedelta(days=2), opened_at),
        patient_mule(world, first + timedelta(days=10), opened_at),
        task_scam(world, first + timedelta(days=21), opened_at),
    )
