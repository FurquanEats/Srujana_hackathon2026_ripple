"""The institutions in the simulated network, read from `network.toml` so the simulator and the nodes share one roster.

Every member that holds customer accounts (the four banks, PaySetu and CoinKosh) is one `Member` here, with the
4-letter code that starts its IFSCs and NEFT and RTGS UTRs, and its UPI handle. The CFCFRMS hub keeps no accounts,
so it is left out. The city is the simulator's own detail, used for ATM and shop locations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ripple_core.network import Kind, Network, load_network

NETWORK_TOML = Path(__file__).resolve().parents[4] / "network.toml"
CITIES = {
    "bank-a": "Mumbai",
    "bank-b": "Patna",
    "bank-c": "Kolkata",
    "bank-d": "Bengaluru",
    "wallet-w": "Noida",
    "exchange-x": "Bengaluru",
}


@dataclass(frozen=True)
class Member:
    id: str  # the member's id in network.toml, for example "bank-a"
    code: str  # 4 capital letters
    kind: Kind
    upi_handle: str
    city: str | None


def account_holders(network: Network) -> tuple[Member, ...]:
    """The members that hold customer accounts, in network.toml's order."""
    out: list[Member] = []
    for m in network.members:
        if m.kind is Kind.HUB:
            continue
        if m.bank_code is None or not m.vpa_handles:
            raise ValueError(
                f"{m.id} holds accounts, so network.toml must give it a bank_code and a UPI handle"
            )
        out.append(Member(m.id, m.bank_code, m.kind, m.vpa_handles[0], CITIES.get(m.id)))
    return tuple(out)


NETWORK = account_holders(load_network(NETWORK_TOML))
BY_ID = {m.id: m for m in NETWORK}
BANKS = tuple(m for m in NETWORK if m.kind is Kind.BANK)


def member(member_id: str) -> Member:
    try:
        return BY_ID[member_id]
    except KeyError:
        raise ValueError(f"no member with id {member_id!r}") from None
