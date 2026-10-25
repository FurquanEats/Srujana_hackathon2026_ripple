"""Write a simulated month to files.

    uv run ripple-sim --seed 7 --out data/sim

`deliveries.jsonl` has one message per line for one member's node, in time order. `story.json` names the demo
story's accounts and payments, and the traced amounts the PRD expects, so an end-to-end test can find them.

TODO(rebuild/node-hub): add `--post` to send each delivery to its member's node, signed as the party "sim".
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from ripple_core.money import fmt_inr, rupees
from ripple_sim.events import AccountOpening
from ripple_sim.scenario import DemoStory
from ripple_sim.simulation import DEFAULT_MONTH, simulate
from ripple_sim.traffic import TrafficConfig

# What the PRD's demo story must trace, under the SOP's victims-first rule.
EXPECTED_TRACED = {
    "m3_to_ravi_traders": rupees("2,00,000"),
    "m3_to_galaxy_mobiles": rupees("50,000"),
    "m3_salary": 0,
}


def story_json(story: DemoStory) -> dict[str, Any]:
    return {
        "ack_number": story.ack_number,
        "reported_at": story.reported_at.isoformat(),
        "accounts": {
            role: {
                "member": a.member.name,
                "holder": a.holder,
                "ifsc": a.ifsc,
                "account_number": a.number,
                "vpa": a.vpa,
            }
            for role, a in story.accounts.items()
        },
        "steps": [
            {
                "name": s.name,
                "payer": s.payer,
                "payee": s.payee,
                "rail": s.payment.rail.value,
                "reference": s.payment.reference,
                "amount": s.payment.amount,
                "at": s.payment.at.isoformat(),
                "exit_identifier": s.exit_identifier,
            }
            for s in story.steps
        ],
        "expected_traced": EXPECTED_TRACED,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ripple-sim", description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--month", type=date.fromisoformat, default=DEFAULT_MONTH, help="any day in the month"
    )
    parser.add_argument("--people-per-bank", type=int, default=60)
    parser.add_argument("--out", type=Path, default=Path("data/sim"))
    args = parser.parse_args(argv)

    sim = simulate(args.seed, TrafficConfig(month=args.month, people_per_bank=args.people_per_bank))
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "deliveries.jsonl").open("w", encoding="utf-8") as f:
        for d in sim.deliveries:
            kind = "account_opening" if isinstance(d.message, AccountOpening) else "ledger_posting"
            line = {"member": d.member, "kind": kind, "message": d.message.model_dump(mode="json")}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    (args.out / "story.json").write_text(json.dumps(story_json(sim.story), indent=2) + "\n", encoding="utf-8")

    openings = sum(isinstance(d.message, AccountOpening) for d in sim.deliveries)
    print(
        f"seed {sim.seed}: {openings} accounts, {len(sim.deliveries) - openings} postings "
        f"({sim.posted} payments and exits posted, {sim.skipped} declined for lack of funds); "
        f"story: {fmt_inr(sim.story.step('victim_to_m1').payment.amount)} reported on {sim.story.ack_number}; "
        f"written to {args.out}"
    )


if __name__ == "__main__":
    main()
