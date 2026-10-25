"""Red team: an adaptive adversary that searches for laundering plans Ripple misses.

A plan is a recipe a mule herder could follow: how many victims, how much each pays, how many hops of mules, how
many ways the money is split at each hop, how long each mule waits before passing it on, what share it passes on,
and how the money is cashed out at the end. The adversary turns each plan into transactions on top of a month of
ordinary simulated traffic, lets the engine score them, and keeps the plans that moved the most money without a
single alert. Each round mutates the best plans so far, like an attacker learning from what got caught.

A plan counts as caught only if some payment reaches the Review tier; a Watch-level flag means "unusual" and nobody
acts on it. The output is not a score to be proud of; it is a map of blind spots. Every evading plan is a concrete scenario the
team can turn into a test and a fix, and the round log shows how quickly an adaptive attacker finds one.
"""

from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta

from ripple.engine import Engine
from ripple.schema import Rail, Transaction

MIN_LAUNDERED = 50_000  # a plan that moves less than this is not worth a criminal's time
ACTED_ON = 0.70  # Review tier: a Watch-level flag means "unusual", which nobody acts on, so it does not count as caught


@dataclass(frozen=True)
class Plan:
    victims: int = 5
    victim_amount: float = 10_000
    hops: int = 2
    split: int = 2
    delay_minutes: int = 10
    pass_share: float = 0.95
    cash_out: str = "atm"  # atm | crypto | none

    def describe(self) -> str:
        return (f"{self.victims} victims x Rs {self.victim_amount:,.0f}, {self.hops} hops, split {self.split} ways, "
                f"wait {self.delay_minutes} min, pass on {self.pass_share:.0%}, cash out via {self.cash_out}")


RANGES = {
    "victims": [1, 2, 3, 4, 5, 6, 8],
    "victim_amount": [4_999, 9_000, 15_000, 25_000, 49_000, 90_000, 150_000],
    "hops": [1, 2, 3, 4],
    "split": [1, 2, 3, 4],
    "delay_minutes": [2, 10, 25, 45, 90, 240, 600, 1440],
    "pass_share": [0.6, 0.75, 0.85, 0.95, 1.0],
    "cash_out": ["atm", "crypto", "none"],
}


def random_plan(rng: random.Random) -> Plan:
    return Plan(**{k: rng.choice(v) for k, v in RANGES.items()})


def mutate(plan: Plan, rng: random.Random) -> Plan:
    field_name = rng.choice(list(RANGES))
    return replace(plan, **{field_name: rng.choice(RANGES[field_name])})


def transactions(plan: Plan, start: datetime, tag: str, victims: list[str],
                 devices: dict[str, str] | None = None) -> list[Transaction]:
    """Turns a plan into time-ordered payments: victims pay the first mule, each mule splits onward after its delay,
    and the last mules cash out."""
    txns: list[Transaction] = []
    n = 0

    def pay(ts: datetime, src: str, dst: str, amount: float, rail: Rail = Rail.IMPS) -> None:
        nonlocal n
        n += 1
        device = (devices or {}).get(src, f"D-{src}")  # victims pay from their usual phone, mules from their own
        txns.append(Transaction(txn_id=f"{tag}-{n}", ts=ts, src_account=src, dst_account=dst, amount=round(amount, 2),
                                rail=rail, device_id=device, location="Kolkata", channel="mobile"))

    first = f"{tag}-M0"
    for i, v in enumerate(victims[: plan.victims]):
        pay(start + timedelta(minutes=7 * i), v, first, plan.victim_amount, Rail.UPI)
    layer = [(first, plan.victims * plan.victim_amount, start + timedelta(minutes=7 * plan.victims))]
    for hop in range(1, plan.hops + 1):
        nxt = []
        for k, (mule, held, ready) in enumerate(layer):
            out = held * plan.pass_share / plan.split
            for s in range(plan.split):
                dst = f"{tag}-M{hop}-{k}-{s}"
                ts = ready + timedelta(minutes=plan.delay_minutes + 3 * s)
                pay(ts, mule, dst, out)
                nxt.append((dst, out, ts))
        layer = nxt
    if plan.cash_out != "none":
        for k, (mule, held, ready) in enumerate(layer):
            ts = ready + timedelta(minutes=plan.delay_minutes)
            if plan.cash_out == "atm":
                pay(ts, mule, f"ATM-{tag}-{k}", held * 0.98, Rail.CASH)
            else:
                pay(ts, mule, f"P2P-USDT-{tag}", held * 0.98)
    return sorted(txns, key=lambda t: t.ts)


@dataclass
class Trial:
    plan: Plan
    max_probability: float
    alerts: int
    laundered: float

    @property
    def evaded(self) -> bool:
        return self.max_probability < ACTED_ON and self.laundered >= MIN_LAUNDERED

    @property
    def fitness(self) -> float:
        """What the attacker wants: enough money moved, with the highest score as low as possible."""
        return min(self.laundered / MIN_LAUNDERED, 1.0) * (1.0 - self.max_probability)


class RedTeam:
    def __init__(self, seed: int = 11, history_days: int = 20) -> None:
        from ripple.sim.india import START, World

        self.rng = random.Random(seed)
        world = World(n_people=80, n_shops=12, seed=seed)
        world.simulate(days=history_days)
        self.base = Engine("india")
        for row in world.sorted_rows():
            self.base.process(row.txn)
        self.start = START + timedelta(days=history_days, hours=10)
        self.victims = [p.account for p in world.people if p.kind == "salaried"]
        self.devices = {p.account: p.device for p in world.people}
        self.trials: list[Trial] = []

    def attack(self, plan: Plan) -> Trial:
        engine = copy.deepcopy(self.base)  # every plan meets the same bank, with the same history
        tag = f"RT{len(self.trials)}"
        victims = self.rng.sample(self.victims, min(plan.victims, len(self.victims)))
        scored = [engine.process(t)[0] for t in transactions(plan, self.start, tag, victims, self.devices)]
        laundered = sum(t.amount for t in scored if t.dst_account.startswith(("ATM-", "P2P-")))
        if plan.cash_out == "none":  # the money that reached the last layer of mules
            last = f"{tag}-M{plan.hops}-"
            laundered = sum(t.amount for t in scored if t.dst_account.startswith(last))
        trial = Trial(plan, round(max(t.probability for t in scored), 4), sum(t.is_alert for t in scored), round(laundered, 2))
        self.trials.append(trial)
        return trial

    def run(self, rounds: int = 6, population: int = 16, keep: int = 4) -> list[dict]:
        log = []
        pool = [random_plan(self.rng) for _ in range(population)]
        for r in range(1, rounds + 1):
            results = [self.attack(p) for p in pool]
            evaded = [t for t in results if t.evaded]
            ranked = sorted(results, key=lambda t: (not t.evaded, -t.laundered if t.evaded else -t.fitness))
            best = ranked[0]
            log.append({
                "round": r,
                "plans": len(results),
                "evaded": len(evaded),
                "caught_share": round(1 - len(evaded) / len(results), 3),
                "best": {"plan": asdict(best.plan), "description": best.plan.describe(), "evaded": best.evaded,
                         "max_probability": best.max_probability, "laundered": best.laundered},
            })
            parents = [t.plan for t in ranked[:keep]]
            pool = parents + [mutate(self.rng.choice(parents), self.rng) for _ in range(population - keep)]
        return log

    def blind_spots(self) -> list[dict]:
        """Every distinct evading plan, most money first."""
        seen, spots = set(), []
        for t in sorted((t for t in self.trials if t.evaded), key=lambda t: -t.laundered):
            if t.plan not in seen:
                seen.add(t.plan)
                spots.append({"plan": asdict(t.plan), "description": t.plan.describe(), "laundered": t.laundered,
                              "max_probability": t.max_probability})
        return spots
