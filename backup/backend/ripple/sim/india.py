"""India transaction simulator: persona accounts doing ordinary UPI, IMPS, NEFT, RTGS and cash business, plus
labelled injectors for the demo's inject buttons.

    python -m ripple.sim.india --out ../data/demo/india_demo.csv

The base month is legitimate. Each injector returns new transactions that start at a given time and reuse persona
accounts, so the engine judges them against real history:

    mule_ring          strangers pay one account, which forwards most of it through two mules to a collector
    scam_fanout        a victim's large transfer lands in a scam account that splits it to fresh payees within an hour
    sim_swap_takeover  a new device in a new city drains a salaried account to a new payee
    cash_structuring   cash deposits just under the Rs 50,000 PAN-quote limit on consecutive days
    diwali_spike       legitimate festival shopping: many people pay jewellers and electronics shops more than usual
    digital_arrest     a pensioner, coached by fake police on a video call, breaks fixed deposits over two days and
                       sends them by RTGS to "safe accounts"; mules split the money onward, cash some out, buy crypto
                       and leave the rest sitting, which is what a freeze can still recover
    patient_ring       a few victims pay one new account, which waits seven to ten hours, splits the money to new mules,
                       and they wait just over a day before withdrawing it as cash: the red team's best plan for
                       evading the built-in detectors, with its amounts, waits and split varied on every run

Every row carries is_laundering (0/1), scenario (the injector name, empty for base traffic), and victim (1 on the
first-hop payment where stolen money starts, with the victim's account in victim_account), so taint tracking knows
where to start. Transaction ignores these columns, so the API can replay the file as is.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ripple.schema import Rail, Transaction

CITIES = ["Bengaluru", "Mumbai", "Delhi", "Chennai", "Hyderabad", "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Kochi"]
START = datetime(2026, 10, 10)
DAYS = 30
DIWALI = datetime(2026, 11, 8)  # Diwali (Lakshmi Puja) 2026
INJECTORS = ["mule_ring", "scam_fanout", "sim_swap_takeover", "cash_structuring", "diwali_spike", "digital_arrest",
             "patient_ring", "fd_broken"]
LABELS = {"fd_broken": 0, "mule_ring": 1, "scam_fanout": 1, "sim_swap_takeover": 1, "cash_structuring": 1, "diwali_spike": 0,
          "digital_arrest": 1, "patient_ring": 1}


@dataclass
class Persona:
    account: str
    kind: str  # salaried | student | gig | pensioner | shop
    city: str
    device: str
    handle: str
    merchants: list[str] = field(default_factory=list)
    contacts: list[str] = field(default_factory=list)


@dataclass
class Row:
    txn: Transaction
    is_laundering: int = 0
    scenario: str = ""
    victim_account: str = ""  # set on the first-hop payment of stolen money


class World:
    def __init__(self, n_people: int = 160, n_shops: int = 30, seed: int = 7) -> None:
        self.rng = random.Random(seed)
        self.rows: list[Row] = []
        self._n = 0
        self._fresh = 0
        kinds = ["salaried"] * 6 + ["student"] * 2 + ["gig"] * 2 + ["pensioner"]
        self.shops = [self._persona(f"SHOP{i:03d}", "shop") for i in range(n_shops)]
        self.jewellers = [f"JEWEL{i:02d}" for i in range(4)]
        self.electronics = [f"ELEC{i:02d}" for i in range(4)]
        self.employers = [f"EMPLOYER{i:02d}" for i in range(6)]
        self.landlords = [f"LANDLORD{i:03d}" for i in range(40)]
        self.people = [self._persona(f"AC{i:04d}", self.rng.choice(kinds)) for i in range(n_people)]
        shop_ids = [s.account for s in self.shops]
        for p in self.people:
            p.merchants = self.rng.sample(shop_ids, 5)
            p.contacts = [c.account for c in self.rng.sample(self.people, 3) if c is not p]

    def _persona(self, account: str, kind: str) -> Persona:
        return Persona(account, kind, self.rng.choice(CITIES), f"D-{account}", f"{account.lower()}@okbank")

    def fresh_account(self, prefix: str = "NEW") -> str:
        self._fresh += 1
        return f"{prefix}{self._fresh:04d}"

    def pay(self, ts: datetime, src: str, dst: str, amount: float, rail: Rail = Rail.UPI, *, device: str | None = None,
            location: str | None = None, handle: str | None = None, label: int = 0, scenario: str = "",
            victim: bool = False) -> Transaction:
        self._n += 1
        txn = Transaction(
            txn_id=f"S{self._n:07d}", ts=ts.replace(microsecond=0), src_account=src, dst_account=dst, amount=round(amount, 2), currency="INR",
            rail=rail, src_handle=handle, device_id=None if rail == Rail.CASH else device, location=location,
            channel="branch" if rail == Rail.CASH else ("netbanking" if rail in (Rail.NEFT, Rail.RTGS) else "mobile"),
        )
        self.rows.append(Row(txn, label, scenario, src if victim else ""))
        return txn

    def by(self, p: Persona, ts: datetime, dst: str, amount: float, rail: Rail = Rail.UPI, **kw) -> Transaction:
        """A payment by persona p from their own phone and city, unless overridden."""
        kw.setdefault("device", p.device)
        kw.setdefault("location", p.city)
        kw.setdefault("handle", p.handle)
        return self.pay(ts, p.account, dst, amount, rail, **kw)

    def _rail_for(self, amount: float) -> Rail:
        if amount >= 200000:
            return Rail.RTGS
        if amount >= 100000:
            return self.rng.choice([Rail.IMPS, Rail.NEFT])
        return Rail.UPI if amount < 25000 or self.rng.random() < 0.7 else Rail.IMPS

    # ---- base month -------------------------------------------------------------------------------------------
    def simulate(self, start: datetime = START, days: int = DAYS) -> None:
        r = self.rng
        for d in range(days):
            day = start + timedelta(days=d)
            for p in self.people:
                spend = {"salaried": (150, 3000), "student": (40, 600), "gig": (80, 1500), "pensioner": (100, 1500)}[p.kind]
                for _ in range(r.choice([1, 2, 2, 3])):
                    t = day + timedelta(hours=r.uniform(7, 22))
                    self.by(p, t, r.choice(p.merchants), r.uniform(*spend))
                if r.random() < 0.15 and p.contacts:  # paying back a friend
                    self.by(p, day + timedelta(hours=r.uniform(9, 23)), r.choice(p.contacts), r.uniform(100, 2000))
                if p.kind == "gig" and r.random() < 0.6:  # daily payout from a platform
                    self.pay(day + timedelta(hours=r.uniform(18, 23)), "PLATFORM01", p.account, r.uniform(400, 2500),
                             Rail.IMPS, location=p.city)
                if p.kind == "student" and d % 30 == 3:
                    self.pay(day + timedelta(hours=11), f"PARENT-{p.account}", p.account, r.uniform(5000, 12000),
                             Rail.UPI, location=p.city)
            if day.day == 1:  # pension, salary, then rent soon after
                for p in (x for x in self.people if x.kind == "pensioner"):
                    self.pay(day + timedelta(hours=8, minutes=r.randint(0, 50)), "PENSION-TREASURY", p.account,
                             r.choice([28000, 36000, 45000]), Rail.NEFT)
                for i, p in enumerate(x for x in self.people if x.kind == "salaried"):
                    salary = r.choice([35000, 52000, 68000, 85000, 120000, 240000])
                    self.pay(day + timedelta(hours=9, minutes=r.randint(0, 50)), self.employers[i % len(self.employers)],
                             p.account, salary, Rail.RTGS if salary >= 200000 else Rail.NEFT)
                    rent = salary * r.uniform(0.25, 0.4)
                    self.by(p, day + timedelta(hours=r.uniform(11, 20)), self.landlords[i % len(self.landlords)], rent,
                            self._rail_for(rent))
            for s in self.shops:  # shops bank their cash a few times a week, and pay suppliers
                if r.random() < 0.4:
                    self.pay(day + timedelta(hours=r.uniform(10, 16)), "CASH", s.account, r.uniform(8000, 90000),
                             Rail.CASH, location=s.city)
                if r.random() < 0.25:
                    amount = r.uniform(20000, 250000)
                    self.by(s, day + timedelta(hours=r.uniform(10, 18)), f"SUPPLIER{r.randint(0, 9):02d}", amount,
                            self._rail_for(amount))

    # ---- injectors --------------------------------------------------------------------------------------------
    def inject(self, kind: str, at: datetime) -> list[Transaction]:
        """Adds one labelled scenario starting at `at` and returns its transactions in time order."""
        if kind not in INJECTORS:
            raise ValueError(f"unknown injector {kind!r}; choose from {INJECTORS}")
        before = len(self.rows)
        getattr(self, f"_{kind}")(at, LABELS[kind], kind)
        return sorted((row.txn for row in self.rows[before:]), key=lambda t: t.ts)

    def _mule_ring(self, t: datetime, label: int, scenario: str) -> None:
        r = self.rng
        mule, hop1, hop2 = r.sample([p for p in self.people if p.kind in ("student", "gig")], 3)
        victims = r.sample([p for p in self.people if p.kind == "salaried" and p not in (mule, hop1, hop2)], 7)
        collector = self.fresh_account("COLL")
        total = 0.0
        for i, v in enumerate(victims):
            amount = r.choice([4999, 7800, 8300, 9500, 11200, 12000, 15000])
            total += amount
            self.by(v, t + timedelta(minutes=17 * i + r.randint(0, 5)), mule.account, amount,
                    label=label, scenario=scenario, victim=True)
        out = t + timedelta(minutes=17 * len(victims) + 6)
        split = round(total * 0.9 * 0.55)
        self.by(mule, out, hop1.account, split, Rail.IMPS, label=label, scenario=scenario)
        self.by(mule, out + timedelta(minutes=2), hop2.account, round(total * 0.9) - split, Rail.IMPS,
                label=label, scenario=scenario)
        self.by(hop1, out + timedelta(minutes=15), collector, split * 0.98, Rail.IMPS, label=label, scenario=scenario)
        self.by(hop2, out + timedelta(minutes=21), collector, (round(total * 0.9) - split) * 0.98, Rail.IMPS,
                label=label, scenario=scenario)

    def _scam_fanout(self, t: datetime, label: int, scenario: str) -> None:
        r = self.rng
        victim = r.choice([p for p in self.people if p.kind == "salaried"])
        scam = self.fresh_account("SCAM")
        amount = r.choice([180000, 250000, 320000])
        # The victim's own payment is genuine (they were tricked), so only the scam account's moves are laundering.
        self.by(victim, t, scam, amount, self._rail_for(amount), scenario=scenario, victim=True)
        parts = [r.uniform(0.8, 1.2) for _ in range(7)]
        for i, w in enumerate(parts):
            self.pay(t + timedelta(minutes=6 + 7 * i), scam, self.fresh_account("NEW"), amount * 0.95 * w / sum(parts),
                     Rail.IMPS, device="D-SCAM-1", location="Jamtara", handle=f"{scam.lower()}@okbank",
                     label=label, scenario=scenario)

    def _sim_swap_takeover(self, t: datetime, label: int, scenario: str) -> None:
        r = self.rng
        p = r.choice([x for x in self.people if x.kind == "salaried"])
        city = r.choice([c for c in CITIES if c != p.city])
        device = f"D-SWAP-{p.account}"
        self.by(p, t, r.choice(p.merchants), 1, device=device, location=city, label=label, scenario=scenario)
        payee = self.fresh_account("NEW")
        self.by(p, t + timedelta(minutes=18), payee, r.choice([95000, 98000]), Rail.IMPS, device=device,
                location=city, label=label, scenario=scenario, victim=True)
        self.by(p, t + timedelta(minutes=26), payee, r.choice([45000, 60000]), Rail.IMPS, device=device,
                location=city, label=label, scenario=scenario, victim=True)

    def _cash_structuring(self, t: datetime, label: int, scenario: str) -> None:
        r = self.rng
        p = r.choice([x for x in self.people if x.kind in ("gig", "student")])
        for i in range(4):
            self.pay(t + timedelta(days=i, hours=r.uniform(0, 3)), "CASH", p.account, r.uniform(45500, 49900),
                     Rail.CASH, location=p.city, label=label, scenario=scenario)

    def _diwali_spike(self, t: datetime, label: int, scenario: str) -> None:
        r = self.rng
        salaried = [x for x in self.people if x.kind == "salaried"]
        for p in r.sample(salaried, min(25, len(salaried))):
            shop = r.choice(self.jewellers + self.electronics)
            amount = r.uniform(15000, 90000)
            self.by(p, t + timedelta(hours=r.uniform(0, 10)), shop, amount, self._rail_for(amount), scenario=scenario)

    def _digital_arrest(self, t: datetime, label: int, scenario: str) -> None:
        r = self.rng
        victims = [p for p in self.people if p.kind == "pensioner"] or [p for p in self.people if p.kind == "salaried"]
        v = r.choice(victims)
        fd = f"FD-{v.account}"
        m = lambda minutes: t + timedelta(minutes=minutes)  # noqa: E731
        mule1, mule2 = self.fresh_account("MULE"), self.fresh_account("MULE")
        layer = [self.fresh_account("MULE") for _ in range(5)]
        tag = {"label": label, "scenario": scenario}
        # Day 1: a fixed deposit broken early (the victim's own money, so not labelled), then sent to a "safe account".
        self.pay(m(0), fd, v.account, 800000, Rail.NEFT, location=v.city, scenario=scenario)
        self.by(v, m(42), mule1, 750000, Rail.RTGS, victim=True, **tag)
        # Mule 1 splits it within half an hour; one leg is cashed out, one buys crypto, one sits.
        for i, (dst, amount) in enumerate(zip(layer[:3], (260000, 250000, 228000))):
            self.pay(m(55 + 6 * i), mule1, dst, amount, Rail.IMPS, device="D-MULE-1", location="Kolkata", **tag)
        self.pay(m(95), layer[0], "ATM-CASH", 95000, Rail.CASH, location="Kolkata", **tag)
        self.pay(m(110), layer[1], "P2P-USDT-07", 245000, Rail.IMPS, device="D-MULE-2", location="Kolkata", **tag)
        # Day 2: a second deposit broken and sent to a new "safe account", split onward within the hour.
        day2 = 24 * 60 - 25
        self.pay(m(day2), fd, v.account, 400000, Rail.NEFT, location=v.city, scenario=scenario)
        self.by(v, m(day2 + 30), mule2, 390000, Rail.RTGS, victim=True, **tag)
        self.pay(m(day2 + 48), mule2, layer[3], 200000, Rail.IMPS, device="D-MULE-3", location="Jamtara", **tag)
        self.pay(m(day2 + 52), mule2, layer[4], 185000, Rail.IMPS, device="D-MULE-3", location="Jamtara", **tag)
        self.pay(m(day2 + 70), layer[3], "P2P-USDT-07", 150000, Rail.IMPS, device="D-MULE-4", location="Jamtara", **tag)

    def _patient_ring(self, t: datetime, label: int, scenario: str) -> None:
        r = self.rng
        victims = r.sample([p for p in self.people if p.kind == "salaried"], r.randint(3, 4))  # under fan-in's five senders
        amount = r.choice([35_000, 42_000, 49_000])
        first = self.fresh_account("MULE")
        for i, v in enumerate(victims):
            self.by(v, t + timedelta(minutes=7 * i + r.randint(0, 4)), first, amount, Rail.UPI,
                    label=label, scenario=scenario, victim=True)
        held = amount * len(victims)
        ready = t + timedelta(minutes=7 * len(victims) + r.randint(7, 10) * 60)  # past pass-through's six hours
        mules = [self.fresh_account("MULE") for _ in range(r.randint(3, 4))]
        for i, mule in enumerate(mules):  # each mule waits just over a day, past the 24-hour cash-out check, then withdraws
            sent = self.pay(ready + timedelta(minutes=3 * i), first, mule, held / len(mules), Rail.IMPS,
                            device=f"D-{first}", location="Kolkata", label=label, scenario=scenario)
            self.pay(sent.ts + timedelta(hours=r.randint(25, 30)), mule, f"ATM-{mule}", sent.amount * 0.98, Rail.CASH,
                     location="Kolkata", label=label, scenario=scenario)

    def _fd_broken(self, t: datetime, label: int, scenario: str) -> None:
        """A pensioner breaks a fixed deposit early, the first step of a digital arrest. Nothing else happens, so a
        pre-payment check can judge the transfer a scammer would ask for next."""
        v = self.rng.choice([p for p in self.people if p.kind == "pensioner"] or [p for p in self.people if p.kind == "salaried"])
        self.pay(t, f"FD-{v.account}", v.account, 800000, Rail.NEFT, location=v.city, label=label, scenario=scenario)

    def sorted_rows(self) -> list[Row]:
        return sorted(self.rows, key=lambda row: row.txn.ts)


def demo_world(seed: int = 7) -> World:
    """The demo month: 30 ordinary days with every injector placed in the last week, after the engine's warm-up."""
    world = World(seed=seed)
    world.simulate()
    end = START + timedelta(days=DAYS)
    world.inject("cash_structuring", end - timedelta(days=6, hours=-10))
    world.inject("mule_ring", end - timedelta(days=4, hours=-14))
    world.inject("sim_swap_takeover", end - timedelta(days=3, hours=-21, minutes=-40))
    world.inject("scam_fanout", end - timedelta(days=2, hours=-11))
    world.inject("diwali_spike", DIWALI + timedelta(hours=9))
    world.inject("digital_arrest", end - timedelta(days=5, hours=-11))
    return world


def to_frame(rows: list[Row]):
    import pandas as pd

    return pd.DataFrame([{**row.txn.model_dump(mode="json"), "is_laundering": row.is_laundering,
                          "scenario": row.scenario, "victim": int(bool(row.victim_account)),
                          "victim_account": row.victim_account} for row in rows])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="../data/demo/india_demo.csv")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    from pathlib import Path

    df = to_frame(demo_world(args.seed).sorted_rows())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"{len(df):,} rows, {df['ts'].min()} to {df['ts'].max()} -> {args.out}")
    print(df[df["scenario"] != ""].groupby("scenario")["is_laundering"].agg(["count", "sum"]).to_string())


if __name__ == "__main__":
    main()
