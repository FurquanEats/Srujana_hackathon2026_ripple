"""Where a service finds its network roster, keys, certificates, database and clock.

`uv run ripple certs` writes everything secret under `.ripple/` at the repository root, which git ignores:

    .ripple/tls/ca.crt                 the project certificate authority
    .ripple/tls/<id>.crt, <id>.key     each service's and client's TLS certificate
    .ripple/keys/<id>.ed25519.pem      each party's message-signing key
    .ripple/keys/keyring.json          every party's public signing key, bound to its owner
    .ripple/data/<id>.sqlite3          each service's own database

`uv run ripple up` passes the clock settings to every process, so they all read the same simulated time.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ripple_core.clock import Clock, SimClock, SystemClock
from ripple_core.network import Member, Network, load_network
from ripple_core.signing import Keyring, SigningKey

CLIENTS = ("sim", "web")  # parties that call services but serve nothing on the network


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def ca_cert(self) -> Path:
        return self.home / "tls" / "ca.crt"

    def tls_cert(self, party: str) -> Path:
        return self.home / "tls" / f"{party}.crt"

    def tls_key(self, party: str) -> Path:
        return self.home / "tls" / f"{party}.key"

    def signing_key(self, party: str) -> Path:
        return self.home / "keys" / f"{party}.ed25519.pem"

    @property
    def keyring(self) -> Path:
        return self.home / "keys" / "keyring.json"

    def database(self, party: str) -> Path:
        return self.home / "data" / f"{party}.sqlite3"


@dataclass(frozen=True)
class ServiceConfig:
    member: Member
    network: Network
    paths: Paths
    clock: Clock


def repo_root() -> Path:
    return Path(os.environ.get("RIPPLE_ROOT", Path.cwd()))


def load_service_config(member_id: str | None = None, root: Path | None = None) -> ServiceConfig:
    root = root or repo_root()
    network = load_network(root / "network.toml")
    member = network.get(member_id or os.environ["RIPPLE_MEMBER"])
    return ServiceConfig(member, network, Paths(root / ".ripple"), clock_from_env())


def clock_from_env() -> Clock:
    start = os.environ.get("RIPPLE_CLOCK_START")
    if not start:
        return SystemClock()
    return SimClock(
        datetime.fromisoformat(start),
        speed=float(os.environ.get("RIPPLE_CLOCK_SPEED", "1")),
        real_anchor=float(os.environ["RIPPLE_CLOCK_ANCHOR"]),
    )


def load_keyring(paths: Paths) -> Keyring:
    ring = Keyring()
    for entry in json.loads(paths.keyring.read_text(encoding="utf-8")):
        ring.add(entry["kid"], entry["owner"], entry["public_pem"].encode("ascii"))
    return ring


def load_signing_key(paths: Paths, party: str) -> SigningKey:
    return SigningKey.from_pem(f"{party}-1", party, paths.signing_key(party).read_bytes())
