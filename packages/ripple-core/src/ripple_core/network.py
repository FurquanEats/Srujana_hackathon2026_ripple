"""Who is on the simulated network and how to reach them.

The roster lives in `network.toml` at the repository root. Each institution and hub runs as its own process on its
own localhost port. Notices are routed by the first four letters of an IFSC or by the handle of a UPI ID.
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ripple_core.messages import AccountRef

Slug = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,30}$")]


class Kind(StrEnum):
    BANK = "bank"
    WALLET = "wallet"
    EXCHANGE = "exchange"
    HUB = "hub"


class Member(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Slug
    name: Annotated[str, Field(min_length=1)]
    kind: Kind
    port: Annotated[int, Field(ge=1024, le=65535)]
    bank_code: Annotated[str, Field(pattern=r"^[A-Z]{4}$")] | None = None
    vpa_handles: tuple[Annotated[str, Field(pattern=r"^[a-z]{2,64}$")], ...] = ()
    on_ripple: bool = True  # False: the institution answers notices by hand (the manual baseline)

    @property
    def url(self) -> str:
        return f"https://127.0.0.1:{self.port}"


class Network(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    members: tuple[Member, ...]

    @model_validator(mode="after")
    def _check(self) -> Self:
        for field in ("id", "port", "bank_code"):
            values = [getattr(m, field) for m in self.members if getattr(m, field) is not None]
            if len(values) != len(set(values)):
                raise ValueError(f"two members share the same {field}")
        handles = [h for m in self.members for h in m.vpa_handles]
        if len(handles) != len(set(handles)):
            raise ValueError("two members share a UPI handle")
        return self

    def get(self, member_id: str) -> Member:
        for m in self.members:
            if m.id == member_id:
                return m
        raise KeyError(member_id)

    def holder_of(self, account: AccountRef) -> Member | None:
        """The institution that holds an account, or None if it is not on the network."""
        for m in self.members:
            if account.ifsc is not None and account.ifsc[:4] == m.bank_code:
                return m
            if account.vpa is not None and account.vpa.split("@", 1)[1].lower() in m.vpa_handles:
                return m
        return None


def load_network(path: Path) -> Network:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return Network.model_validate({"members": data.get("member", [])})
