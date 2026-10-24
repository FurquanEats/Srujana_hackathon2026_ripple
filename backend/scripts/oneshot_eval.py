"""Measures one-shot pattern learning and writes data/oneshot.json.

    python scripts/oneshot_eval.py

1. The red team's best evading plan is run once against the India engine: no payment reaches Review. That trail is
   the single example, and Ripple learns a motif from it against the bank's own 20-day history.
2. Generalisation: random laundering plans from the red team's whole search space are run with and without the motif.
3. Adaptive attacker: the red team's full search is rerun against the engine with the motif deployed.
4. False alarms on unseen traffic: a different simulated bank (another seed) is replayed with the motif deployed, and
   every alert the motif adds on legitimate traffic is counted.
"""

from __future__ import annotations

import copy
import json
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ripple.engine import Engine  # noqa: E402
from ripple.motifs import Motif  # noqa: E402
from ripple.redteam import ACTED_ON, Plan, RedTeam, random_plan, transactions  # noqa: E402
from ripple.sim.india import INJECTORS, LABELS, START, World  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "oneshot.json"
EXAMPLE = Plan(victims=6, victim_amount=49_000, hops=2, split=4, delay_minutes=1440, pass_share=1.0, cash_out="atm")


def peak(engine: Engine, plan: Plan, tag: str, team: RedTeam, rng: random.Random) -> float:
    run = copy.deepcopy(engine)
    victims = rng.sample(team.victims, min(plan.victims, len(team.victims)))
    return max(run.process(t)[0].probability for t in transactions(plan, team.start, tag, victims, team.devices))


def with_motif(engine: Engine, motif: Motif) -> Engine:
    armed = copy.deepcopy(engine)
    armed.motifs.motifs[motif.motif_id] = copy.deepcopy(motif)
    return armed


def unseen_bank(motif: Motif, seed: int = 99) -> dict:
    """Replays a different simulated bank, with one of each scenario injected, and compares alerts with and without
    the motif."""
    world = World(seed=seed)
    world.simulate()
    day = START + timedelta(days=22, hours=10)
    for i, kind in enumerate(INJECTORS):
        world.inject(kind, day + timedelta(hours=14 * i))
    rows = world.sorted_rows()
    out = {}
    for name, engine in (("without", Engine("india")), ("with", with_motif(Engine("india"), motif))):
        motif_alerts_legit = 0
        legit_alerts = 0
        caught: dict[str, bool] = {k: False for k in INJECTORS if LABELS[k]}
        for row in rows:
            scored, _ = engine.process(row.txn)
            if scored.probability < ACTED_ON or engine.warming_up(scored.ts):
                continue
            if row.is_laundering:
                caught[row.scenario] = True
            elif not row.scenario:
                legit_alerts += 1
                motif_alerts_legit += any(r.code.startswith("motif:") for r in scored.reasons)
        out[name] = {"legit_alerts": legit_alerts, "motif_alerts_on_legit": motif_alerts_legit, "scenarios_caught": caught}
    days = (rows[-1].txn.ts - rows[0].txn.ts).total_seconds() / 86400
    return {"seed": seed, "days": round(days, 1), "transactions": len(rows), **out}


def main() -> None:
    t0 = time.perf_counter()
    team = RedTeam(seed=11)
    rng = random.Random(5)

    learner = copy.deepcopy(team.base)
    victims = rng.sample(team.victims, EXAMPLE.victims)
    example = transactions(EXAMPLE, team.start, "EX", victims, team.devices)
    example_peak = max(learner.process(t)[0].probability for t in example)
    motif = learner.motifs.learn({t.txn_id for t in example}, "one confirmed trail (red-team plan, 0 alerts)")
    motif.deployed = True
    print("learned", motif.name, [c.describe() for c in motif.constraints], f"{motif.false_alarms_per_day:.2f}/day")

    armed = with_motif(team.base, motif)
    plans = [random_plan(rng) for _ in range(120)]
    before = [peak(team.base, p, f"G{i}a", team, rng) for i, p in enumerate(plans)]
    after = [peak(armed, p, f"G{i}b", team, rng) for i, p in enumerate(plans)]
    missed = [i for i, b in enumerate(before) if b < ACTED_ON]
    generalisation = {
        "plans": len(plans),
        "caught_without": sum(b >= ACTED_ON for b in before),
        "caught_with": sum(a >= ACTED_ON for a in after),
        "missed_without": len(missed),
        "of_missed_caught_with": sum(after[i] >= ACTED_ON for i in missed),
    }
    print("generalisation", generalisation)

    adaptive = {}
    for name, defended in (("without", None), ("with", motif)):
        attacker = RedTeam(seed=11)
        if defended is not None:
            attacker.base = with_motif(attacker.base, defended)
        attacker.run(rounds=8, population=24)
        spots = attacker.blind_spots()
        adaptive[name] = {
            "plans_tried": len(attacker.trials),
            "evading_plans": len(spots),
            "caught_share": round(1 - sum(t.evaded for t in attacker.trials) / len(attacker.trials), 3),
            "top_blind_spots": spots[:3],
        }
        print("adaptive", name, {k: v for k, v in adaptive[name].items() if k != "top_blind_spots"})

    unseen = unseen_bank(motif)
    print("unseen bank", {k: v for k, v in unseen.items()})

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "example": {"plan": EXAMPLE.describe(), "peak_probability": round(example_peak, 4), "transactions": len(example)},
        "motif": {
            "name": motif.name,
            "constraints": [{"feature": c.feature, "text": c.describe(), "background_share": c.background_share}
                            for c in motif.constraints],
            "steps": motif.steps,
            "background_events": motif.background_events,
            "background_days": motif.background_days,
            "false_alarms_per_day": round(motif.false_alarms_per_day, 3),
            "lead_hours": motif.lead_hours,
        },
        "generalisation": generalisation,
        "adaptive_red_team": adaptive,
        "unseen_bank": unseen,
        "seconds": round(time.perf_counter() - t0, 1),
        "notes": [
            "Everything here is on simulated Indian bank traffic; the red team's plans are synthetic.",
            "Caught means some payment of the plan reached the Review tier (probability 0.70 or more).",
            "The unseen bank is a different random seed, so the motif's false alarms there were never seen while learning.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"done in {report['seconds']} s -> {OUT}")


if __name__ == "__main__":
    main()
