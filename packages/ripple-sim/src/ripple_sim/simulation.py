"""Put the month and the demo story together into one ordered stream of deliveries."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ripple_core.clock import IST
from ripple_core.messages import LedgerPosting
from ripple_sim.events import Delivery
from ripple_sim.identifiers import SeededIds
from ripple_sim.network import member
from ripple_sim.scenario import DemoStory, open_story_accounts, play_demo_story
from ripple_sim.traffic import Population, TrafficConfig, run_month
from ripple_sim.world import World

DEFAULT_MONTH = date(2026, 11, 1)
DEFAULT_STORY_DAY = 18
STORY_TIME = time(11, 2)


@dataclass(frozen=True)
class Simulation:
    seed: int
    deliveries: tuple[Delivery, ...]
    story: DemoStory
    population: Population
    posted: int
    skipped: int

    def for_member(self, name: str) -> list[Delivery]:
        return [d for d in self.deliveries if d.member == name]


def simulate(
    seed: int = 7, config: TrafficConfig | None = None, story_at: datetime | None = None
) -> Simulation:
    config = config or TrafficConfig(month=DEFAULT_MONTH)
    story_at = story_at or datetime.combine(config.month.replace(day=DEFAULT_STORY_DAY), STORY_TIME, IST)
    rng = random.Random(seed)  # noqa: S311  a reproducible simulation, not security
    world = World(SeededIds(rng, seed))

    population, posted, skipped = run_month(world, rng, config)
    story_accounts = open_story_accounts(world, story_at - timedelta(days=200))
    story = play_demo_story(world, story_accounts, story_at)
    return Simulation(seed, _in_ledger_order(world.deliveries, seed), story, population, posted, skipped)


def _in_ledger_order(deliveries: list[Delivery], seed: int) -> tuple[Delivery, ...]:
    """Order everything by time and number each member's postings in that order.

    The month and the story are posted separately, so posting numbers are given out again here: within each
    member, a later posting always has a higher transaction ID, as on a real statement. A payment's two postings
    keep their order (debit first), because the sort is stable. The seed is part of each ID, so several seeds can
    be posted to one network.
    """
    ordered = sorted(deliveries, key=lambda d: d.at)
    counters: dict[str, int] = {}
    out: list[Delivery] = []
    for d in ordered:
        m = d.message
        if isinstance(m, LedgerPosting):
            code = member(d.member).code
            counters[code] = counters.get(code, 0) + 1
            renumbered = m.model_copy(update={"txn_id": f"{code}-{seed}-{counters[code]:09d}"})
            out.append(Delivery(member=d.member, message=renumbered))
        else:
            out.append(d)
    return tuple(out)
