"""The institutions in the simulated network.

The PRD's network has four banks, a wallet and a crypto exchange, plus the CFCFRMS hub, which keeps no customer
accounts. Each member has a 4-letter code that starts its IFSCs and NEFT and RTGS UTRs, and a UPI handle.

TODO(rebuild/node-hub): read these from network.toml at the repository root once that pull request lands, so the
simulator and the nodes share one definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MemberKind(StrEnum):
    BANK = "bank"
    WALLET = "wallet"
    EXCHANGE = "exchange"


@dataclass(frozen=True)
class Member:
    name: str  # the service name, for example "bank-a"
    code: str  # 4 capital letters
    kind: MemberKind
    display_name: str
    upi_handle: str
    city: str


NETWORK: tuple[Member, ...] = (
    Member("bank-a", "BKAA", MemberKind.BANK, "Bank A", "banka", "Mumbai"),
    Member("bank-b", "BKBB", MemberKind.BANK, "Bank B", "bankb", "Patna"),
    Member("bank-c", "BKCC", MemberKind.BANK, "Bank C", "bankc", "Kolkata"),
    Member("bank-d", "BKDD", MemberKind.BANK, "Bank D", "bankd", "Bengaluru"),
    Member("wallet-w", "WLTW", MemberKind.WALLET, "Wallet W", "walletw", "Noida"),
    Member("exchange-x", "XCHX", MemberKind.EXCHANGE, "Exchange X", "exchx", "Bengaluru"),
)

BY_NAME = {m.name: m for m in NETWORK}
BANKS = tuple(m for m in NETWORK if m.kind is MemberKind.BANK)


def member(name: str) -> Member:
    try:
        return BY_NAME[name]
    except KeyError:
        raise ValueError(f"no member named {name!r}") from None
