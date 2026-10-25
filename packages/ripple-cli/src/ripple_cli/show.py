"""`ripple demo`: run the demo story on the live network over mutual TLS and print the money trail."""

from __future__ import annotations

import secrets
import ssl
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

from ripple_cli import demo
from ripple_core.clock import IST, SimClock
from ripple_core.ids import ComplaintChannel, new_ncrp_ack
from ripple_core.money import fmt_inr
from ripple_core.network import Network
from ripple_core.signing import MemoryReplayGuard, Opened
from ripple_hubs.cfcfrms import Trail
from ripple_service.config import Paths, load_keyring, load_signing_key
from ripple_service.transport import Courier, Envelopes, mtls_post

COMPLAINT_DELAY = timedelta(minutes=12)


def network_now(network: Network, paths: Paths) -> datetime:
    context = ssl.create_default_context(cafile=str(paths.ca_cert))
    context.load_cert_chain(str(paths.tls_cert("sim")), str(paths.tls_key("sim")))
    response = httpx.get(network.get("cfcfrms").url + "/v1/health", verify=context, timeout=5)
    response.raise_for_status()
    return datetime.fromisoformat(response.json()["now"])


def run_demo(network: Network, paths: Paths) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the rupee sign on Windows consoles
    try:
        now = network_now(network, paths)
    except (httpx.HTTPError, OSError) as exc:
        print(f"The network is not running ({exc}). Start it with `uv run ripple up` first.", file=sys.stderr)
        return 1
    clock = SimClock(now)  # follows the network's clock, which `ripple demo` expects to run at speed 1
    keyring = load_keyring(paths)
    couriers = {
        party: Courier(
            Envelopes(load_signing_key(paths, party), keyring, clock, MemoryReplayGuard()),
            mtls_post(network, paths, party),
        )
        for party in ("sim", "web")
    }

    def call(sender: str, member: str, path: str, payload: BaseModel | dict[str, Any]) -> Opened:
        return couriers[sender].call(member, path, payload)

    run = f"{secrets.randbelow(10**6):06d}"
    story = demo.seed(call, now - COMPLAINT_DELAY, run)
    ack = new_ncrp_ack(ComplaintChannel.HELPLINE_1930)
    started = time.perf_counter()
    call("web", "cfcfrms", "/v1/complaints", story.complaint(ack, clock.now()))
    trail = None
    for _ in range(80):
        trail = Trail.model_validate(call("web", "cfcfrms", "/v1/trails", {"ack_number": ack}).payload)
        if trail.complete:
            break
        time.sleep(0.25)
    elapsed = time.perf_counter() - started
    if trail is None:
        return 1
    print_trail(network, story, trail, elapsed)
    return 0 if trail.complete else 1


def print_trail(network: Network, story: demo.Story, trail: Trail, elapsed: float) -> None:
    paid_at = story.victim_payment.at.astimezone(IST).strftime("%H:%M")
    members = {a.member for a in trail.accounts if a.member}
    print()
    print(f"A retired teacher sent {fmt_inr(story.victim_payment.amount)} by RTGS from Navodaya Bank to a mule at "
          f"Meridian Bank at {paid_at} IST, and called 1930 twelve minutes later.")  # fmt: skip
    print(f"Complaint {trail.ack_number}: trail {'complete' if trail.complete else 'NOT complete'} in "
          f"{elapsed:.2f} s across {len(members)} institutions, every bank answering automatically.")  # fmt: skip
    print()
    print(
        f"{'Layer':<6}{'Institution':<14}{'Account holder':<33}{'Victim money in':>16}{'Liened':>12}  Cashed out"
    )
    for a in trail.accounts:
        institution = network.get(a.member).name.split(",")[0] if a.member else "off network"
        exits = ", ".join(f"{fmt_inr(e.traced_amount)} at ATM {e.identifier} ({e.location})" for e in a.exits)
        held = fmt_inr(a.held) if a.held else "-"
        print(f"{a.layer:<6}{institution:<14}{story.holder(a.account.account_number):<33}"
              f"{fmt_inr(a.traced_in):>16}{held:>12}  {exits}")  # fmt: skip
    print()
    print(f"Reported {fmt_inr(trail.reported)}: held {fmt_inr(trail.held)}, cashed out {fmt_inr(trail.cashed_out)}, "
          f"off network {fmt_inr(trail.off_network)}, not found {fmt_inr(trail.not_found)}, "
          f"waiting {fmt_inr(trail.waiting)}.")  # fmt: skip
    on_trail = {a.account.account_number for a in trail.accounts}
    untouched = [p.holder for p in story.parties.values() if p.ref.account_number not in on_trail
                 and p.key not in {"victim"}]  # fmt: skip
    print(
        "Liens cover only the victim's money, so M3's own money stays free. "
        + ", ".join(untouched)
        + " received none of the victim's money, so no notice was sent."
    )
