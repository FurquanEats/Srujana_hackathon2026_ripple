"""Write a simulated month to files, and optionally post it to the running network.

    uv run ripple-sim --seed 7 --out data/sim
    uv run ripple-sim --seed 7 --out data/sim --post

`deliveries.jsonl` has one message per line for one member's node, in time order. `story.json` names the demo
story's accounts and payments, and the traced amounts the PRD expects, so an end-to-end test can find them.
`scams.json` does the same for the other scam shapes (`scams.py`), with each victim's complaint.
`--post` also sends every delivery to its member's node over mutual TLS, signed as the party "sim"; start the
network with `uv run ripple up` first. Without `--month` it then simulates the last full month before the
network's clock, because nodes trace only what has already happened. Each node refuses an account it already
holds, so post a seed only once to a network.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from ripple_core.messages import AccountOpening
from ripple_core.money import fmt_inr, rupees
from ripple_service.config import repo_root
from ripple_sim import post
from ripple_sim.scams import Scam
from ripple_sim.scenario import DemoStory, Step
from ripple_sim.simulation import DEFAULT_MONTH, simulate
from ripple_sim.traffic import TrafficConfig
from ripple_sim.world import Account

# What the PRD's demo story must trace, under the SOP's victims-first rule.
EXPECTED_TRACED = {
    "m3_to_ravi_traders": rupees("2,00,000"),
    "m3_to_galaxy_mobiles": rupees("50,000"),
    "m3_salary": 0,
}


def _accounts_json(accounts: dict[str, Account]) -> dict[str, Any]:
    return {
        role: {
            "member": a.member.id,
            "holder": a.holder,
            "ifsc": a.ifsc,
            "account_number": a.number,
            "vpa": a.vpa,
        }
        for role, a in accounts.items()
    }


def _steps_json(steps: tuple[Step, ...]) -> list[dict[str, Any]]:
    return [
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
        for s in steps
    ]


def story_json(story: DemoStory) -> dict[str, Any]:
    return {
        "ack_number": story.ack_number,
        "reported_at": story.reported_at.isoformat(),
        "accounts": _accounts_json(story.accounts),
        "steps": _steps_json(story.steps),
        "expected_traced": EXPECTED_TRACED,
    }


def scams_json(scams: tuple[Scam, ...]) -> list[dict[str, Any]]:
    return [
        {
            "name": scam.name,
            "accounts": _accounts_json(scam.accounts),
            "steps": _steps_json(scam.steps),
            "reports": [
                {
                    "ack_number": r.ack_number,
                    "victim": r.victim,
                    "steps": list(r.steps),
                    "reported_at": r.reported_at.isoformat(),
                }
                for r in scam.reports
            ],
        }
        for scam in scams
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ripple-sim", description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--month",
        type=date.fromisoformat,
        help=f"any day in the month (default {DEFAULT_MONTH:%Y-%m}, or with --post the last full month before "
        "the network's clock)",
    )
    parser.add_argument("--people-per-bank", type=int, default=60)
    parser.add_argument("--out", type=Path, default=Path("data/sim"))
    parser.add_argument("--post", action="store_true", help="also send every delivery to its member's node")
    parser.add_argument("--batch-size", type=int, default=200, help="ledger postings per request with --post")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the rupee sign on Windows consoles

    live = None
    if args.post:
        try:
            live = post.connect(repo_root())
        except (ConnectionError, OSError, httpx.HTTPError) as exc:
            print(
                f"The network is not running ({exc}). Start it with `uv run ripple up` first.",
                file=sys.stderr,
            )
            return 1
    month = args.month or (post.month_before(live.now) if live else DEFAULT_MONTH)
    sim = simulate(args.seed, TrafficConfig(month=month, people_per_bank=args.people_per_bank))
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "deliveries.jsonl").open("w", encoding="utf-8") as f:
        for d in sim.deliveries:
            kind = "account_opening" if isinstance(d.message, AccountOpening) else "ledger_posting"
            line = {"member": d.member, "kind": kind, "message": d.message.model_dump(mode="json")}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    (args.out / "story.json").write_text(json.dumps(story_json(sim.story), indent=2) + "\n", encoding="utf-8")
    (args.out / "scams.json").write_text(json.dumps(scams_json(sim.scams), indent=2) + "\n", encoding="utf-8")

    openings = sum(isinstance(d.message, AccountOpening) for d in sim.deliveries)
    print(
        f"seed {sim.seed}: {openings} accounts, {len(sim.deliveries) - openings} postings "
        f"({sim.posted} payments and exits posted, {sim.skipped} declined for lack of funds); "
        f"story: {fmt_inr(sim.story.step('victim_to_m1').payment.amount)} reported on {sim.story.ack_number}; "
        f"written to {args.out}"
    )
    if live is None:
        return 0
    if sim.deliveries[-1].at > live.now:
        print(
            f"Not posted: the simulation runs to {sim.deliveries[-1].at:%Y-%m-%d %H:%M %Z}, after the network's "
            f"clock ({live.now:%Y-%m-%d %H:%M %Z}), and nodes cannot trace money they have not seen arrive yet. "
            "Pass an earlier --month.",
            file=sys.stderr,
        )
        return 1
    try:
        posted = post.post(sim.deliveries, live.send, args.batch_size)
    except ConnectionError as exc:
        print(f"Posting failed: {exc}. Each node refuses an account it already holds, so post a seed only once.",
              file=sys.stderr)  # fmt: skip
        return 1
    print(
        f"posted {posted.accounts} accounts and {posted.postings} ledger postings "
        f"in {posted.batches} batches, signed as sim"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
