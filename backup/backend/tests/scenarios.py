"""Small hand-built transaction scenarios for engine tests, each on top of 21 days of ordinary history."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from ripple.schema import Rail, Transaction

T0 = datetime(2026, 10, 1, 9, 0)
DAY = timedelta(days=1)
RING_DAY = T0 + 21 * DAY  # 22 Oct 2026, 09:00


class Builder:
    def __init__(self, seed: int = 1) -> None:
        self.txns: list[Transaction] = []
        self.rng = random.Random(seed)
        self._n = 0

    def pay(self, ts, src, dst, amount, rail=Rail.UPI, device="auto", location="Bengaluru") -> Transaction:
        self._n += 1
        txn = Transaction(
            txn_id=f"T{self._n:06d}",
            ts=ts,
            src_account=src,
            dst_account=dst,
            amount=amount,
            rail=rail,
            device_id=f"D-{src}" if device == "auto" and rail != Rail.CASH else (None if device == "auto" else device),
            location=location,
            channel="branch" if rail == Rail.CASH else "mobile",
        )
        self.txns.append(txn)
        return txn

    def history(self, account: str, days: int = 21, low: float = 200, high: float = 2500, per_day: int = 2) -> None:
        """Ordinary spending at a few regular merchants, plus a small payment in from a known contact each day."""
        merchants = [f"M-{account}-{i}" for i in range(4)]
        for d in range(days):
            day = T0 + d * DAY
            for k in range(per_day):
                self.pay(day + timedelta(hours=1 + 4 * k, minutes=self.rng.randint(0, 50)), account,
                         self.rng.choice(merchants), round(self.rng.uniform(low, high)))
            self.pay(day + timedelta(hours=10), f"K-{account}", account, round(self.rng.uniform(200, 600)))

    def sorted(self) -> list[Transaction]:
        return sorted(self.txns, key=lambda t: t.ts)


def mule_ring(b: Builder) -> dict[str, list[str]]:
    """Seven strangers pay A2217 over two hours; it forwards 90% to two mules, which pass it to collector A9001."""
    b.history("A2217", low=100, high=600, per_day=1)
    victims = [f"V{i}" for i in range(1, 8)]
    for v in victims:
        b.history(v)
    t = RING_DAY + timedelta(hours=5)  # 14:00
    ins = [b.pay(t + timedelta(minutes=18 * i), v, "A2217", a).txn_id
           for i, (v, a) in enumerate(zip(victims, [9500, 12000, 4999, 15000, 7800, 11200, 8300]))]
    out1 = b.pay(t + timedelta(minutes=114), "A2217", "A5120", 36000).txn_id
    out2 = b.pay(t + timedelta(minutes=116), "A2217", "A5121", 26000).txn_id
    hop1 = b.pay(t + timedelta(minutes=130), "A5120", "A9001", 35500, rail=Rail.IMPS).txn_id
    hop2 = b.pay(t + timedelta(minutes=135), "A5121", "A9001", 25700, rail=Rail.IMPS).txn_id
    return {"in": ins, "out": [out1, out2], "hop": [hop1, hop2]}


def legit_big_payment(b: Builder) -> str:
    """A salaried customer pays a large one-off amount (Diwali jewellery) to a new merchant."""
    b.history("S1", low=300, high=3000)
    return b.pay(RING_DAY + timedelta(hours=8), "S1", "JEWELLER", 120000).txn_id


def salary_then_rent(b: Builder) -> str:
    """Salary from a known employer, then rent to the usual landlord minutes later: not a mule."""
    b.history("S2", low=300, high=3000)
    for month_day in (0, 21):
        day = T0 + month_day * DAY
        b.pay(day + timedelta(hours=9, minutes=30), "EMPLOYER", "S2", 85000, rail=Rail.NEFT)
        rent = b.pay(day + timedelta(hours=9, minutes=40), "S2", "LANDLORD", 70000)
    return rent.txn_id


def cash_structuring(b: Builder) -> list[str]:
    b.history("A3141", low=500, high=5000)
    amounts = [49000, 49500, 48800, 49900]
    return [b.pay(RING_DAY + timedelta(days=i, hours=2), "CASH", "A3141", a, rail=Rail.CASH).txn_id for i, a in enumerate(amounts[:3])]


def device_takeover(b: Builder) -> str:
    b.history("U1", low=200, high=4000)
    b.pay(RING_DAY + timedelta(hours=16, minutes=12), "U1", "M-U1-0", 150, device="D88")
    return b.pay(RING_DAY + timedelta(hours=16, minutes=30), "U1", "X-NEW", 95000, device="D88").txn_id


def cycle(b: Builder) -> list[str]:
    for a in ("C1", "C2", "C3", "C4"):
        b.history(a)
    t = RING_DAY + timedelta(hours=3)
    legs = [("C1", "C2", 200000), ("C2", "C3", 196000), ("C3", "C4", 193000), ("C4", "C1", 190000)]
    return [b.pay(t + timedelta(hours=3 * i), s, d, a, rail=Rail.IMPS).txn_id for i, (s, d, a) in enumerate(legs)]


def scatter_gather(b: Builder) -> list[str]:
    for a in ("G0", "G1", "G2", "G3", "G9"):
        b.history(a)
    t = RING_DAY + timedelta(hours=2)
    out = [b.pay(t + timedelta(minutes=10 * i), "G0", m, 50000).txn_id for i, m in enumerate(("G1", "G2", "G3"))]
    back = [b.pay(t + timedelta(hours=4, minutes=10 * i), m, "G9", 49000).txn_id for i, m in enumerate(("G1", "G2", "G3"))]
    return out + back


def fan_out(b: Builder) -> str:
    b.history("F1", low=200, high=2000)
    t = RING_DAY + timedelta(hours=6)
    return [b.pay(t + timedelta(minutes=7 * i), "F1", f"NEW{i}", 9000) for i in range(6)][-1].txn_id
