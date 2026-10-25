"""Send a simulation to the members' nodes, signed as the party "sim", so the nodes hold the simulated ledgers.

Accounts go to `/v1/accounts` one at a time. Ledger postings go to `/v1/postings` in batches, in each member's own
order, and a member's pending postings are always sent before it opens another account. A batch is all or
nothing: the node refuses it (409) if any posting conflicts, for example a debit that would touch liened money.

Nodes trace only what has happened by their own clock, so everything posted must be dated before the network's
clock: a credit dated in the node's future cannot be traced.
"""

from __future__ import annotations

import ssl
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from ripple_core.clock import IST, SimClock
from ripple_core.messages import AccountOpening, LedgerPosting
from ripple_core.network import Kind, Network, load_network
from ripple_core.signing import MemoryReplayGuard, Opened
from ripple_service.config import Paths, load_keyring, load_signing_key
from ripple_service.transport import Courier, Envelopes, mtls_post
from ripple_sim.events import Delivery

SIMULATOR = "sim"
Send = Callable[[str, str, BaseModel | dict[str, Any]], Opened]  # (member id, path, payload) -> signed reply


@dataclass(frozen=True)
class Posted:
    accounts: int
    postings: int
    batches: int


def post(deliveries: Iterable[Delivery], send: Send, batch_size: int = 200) -> Posted:
    """Open every account and post every ledger line, keeping each member's order."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    pending: dict[str, list[LedgerPosting]] = {}
    accounts = postings = batches = 0

    def flush(member: str) -> None:
        nonlocal batches
        batch = pending.pop(member, [])
        if batch:
            send(member, "/v1/postings", {"postings": [p.model_dump(mode="json") for p in batch]})
            batches += 1

    for d in deliveries:
        if isinstance(d.message, AccountOpening):
            flush(d.member)
            send(d.member, "/v1/accounts", d.message)
            accounts += 1
        else:
            pending.setdefault(d.member, []).append(d.message)
            postings += 1
            if len(pending[d.member]) >= batch_size:
                flush(d.member)
    for member in list(pending):
        flush(member)
    return Posted(accounts, postings, batches)


def network_now(network: Network, paths: Paths) -> datetime:
    """The network's clock, read from the CFCFRMS hub over mutual TLS, so envelopes are fresh to the nodes."""
    hub = next(m for m in network.members if m.kind is Kind.HUB)
    context = ssl.create_default_context(cafile=str(paths.ca_cert))
    context.load_cert_chain(str(paths.tls_cert(SIMULATOR)), str(paths.tls_key(SIMULATOR)))
    response = httpx.get(hub.url + "/v1/health", verify=context, timeout=5)
    response.raise_for_status()
    return datetime.fromisoformat(response.json()["now"])


@dataclass(frozen=True)
class Live:
    """The running network: how to send to it, and its clock when we connected."""

    send: Send
    now: datetime


def connect(root: Path) -> Live:  # pragma: no cover - needs the live network from `ripple up`
    """Connect to the network that `uv run ripple up` started from `root`."""
    network = load_network(root / "network.toml")
    paths = Paths(root / ".ripple")
    now = network_now(network, paths)
    envelopes = Envelopes(
        load_signing_key(paths, SIMULATOR), load_keyring(paths), SimClock(now), MemoryReplayGuard()
    )
    return Live(Courier(envelopes, mtls_post(network, paths, SIMULATOR)).call, now)


def month_before(now: datetime) -> date:
    """The first day of the last full month before `now` (IST), so a whole simulated month is in the past."""
    first = now.astimezone(IST).date().replace(day=1)
    return (first - timedelta(days=1)).replace(day=1)
