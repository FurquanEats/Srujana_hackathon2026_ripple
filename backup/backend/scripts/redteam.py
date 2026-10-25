"""Runs the adaptive red team against the India engine and writes data/redteam.json.

    python scripts/redteam.py --rounds 8 --population 24
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ripple.redteam import MIN_LAUNDERED, RedTeam  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "redteam.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=8)
    parser.add_argument("--population", type=int, default=24)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    team = RedTeam(seed=args.seed)
    log = team.run(rounds=args.rounds, population=args.population)
    spots = team.blind_spots()
    tried = len(team.trials)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "plans_tried": tried,
        "evading_plans": len(spots),
        "caught_share": round(1 - sum(t.evaded for t in team.trials) / tried, 3),
        "min_laundered": MIN_LAUNDERED,
        "rounds": log,
        "blind_spots": spots[:10],
        "note": "Plans that moved at least Rs 50,000 without any payment reaching Review. Each is a scenario to turn into a test and a fix.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for r in log:
        print(r["round"], r["evaded"], "/", r["plans"], "evaded |", r["best"]["description"], "| p", r["best"]["max_probability"])
    print("blind spots:", len(spots))
    for s in spots[:6]:
        print("  ", s["description"], "| laundered", s["laundered"], "| max p", s["max_probability"])


if __name__ == "__main__":
    main()
