"""An in-process network for tests: every member's real app, wired together without sockets.

Each member gets its own in-memory database, signing key and replay store, exactly as in `ripple up`; only the
transport differs (Starlette's test client instead of HTTPS with mutual TLS).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel

from ripple_core.clock import FixedClock
from ripple_core.messages import AccountOpening, AccountRef, ExitDetail, LedgerPosting, Payment
from ripple_core.network import Kind, Network, load_network
from ripple_core.signing import Keyring, MemoryReplayGuard, Opened, SigningKey
from ripple_hubs.cfcfrms import HubBase, Tracer
from ripple_hubs.cfcfrms import build_app as build_hub
from ripple_hubs.dpip import Dpip, DpipBase
from ripple_node.app import NodeContext
from ripple_node.app import build_app as build_node
from ripple_node.ledger import NodeBase
from ripple_service.config import CLIENTS
from ripple_service.db import init_db, make_engine
from ripple_service.transport import Courier, Envelopes, RemoteError

ROOT = Path(__file__).resolve().parents[3]


DPIP_KEY = b"ripple-test-dpip-key"  # the gateway's default key in tests


@dataclass
class Net:
    clock: FixedClock
    network: Network = field(default_factory=lambda: load_network(ROOT / "network.toml"))
    keys: dict[str, SigningKey] = field(default_factory=dict)
    keyring: Keyring = field(default_factory=Keyring)
    clients: dict[str, TestClient] = field(default_factory=dict)
    node_contexts: dict[str, NodeContext] = field(default_factory=dict)
    tracer: Tracer | None = None
    seq: int = 0

    def __post_init__(self) -> None:
        for party in [m.id for m in self.network.members] + list(CLIENTS):
            key = SigningKey.generate(f"{party}-1", party)
            self.keys[party] = key
            self.keyring.add(key.kid, party, key.public_pem())
        for member in self.network.members:
            if member.kind is Kind.HUB:
                factory = init_db(make_engine(None), HubBase.metadata, DpipBase.metadata)
                self.tracer = Tracer(
                    factory, Courier(self.envelopes(member.id), self.post), self.network, self.clock
                )
                dpip = Dpip(factory, DPIP_KEY, self.clock)
                app = build_hub(self.tracer, self.envelopes(member.id), dpip)
            else:
                factory = init_db(make_engine(None), NodeBase.metadata)
                ctx = NodeContext(member.id, factory, self.envelopes(member.id), self.clock)
                self.node_contexts[member.id] = ctx
                app = build_node(ctx)
            self.clients[member.id] = TestClient(app)

    def envelopes(self, party: str) -> Envelopes:
        return Envelopes(self.keys[party], self.keyring, self.clock, MemoryReplayGuard())

    def post(self, to: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self.clients[to].post(path, json=body)
        if response.is_error:
            detail = response.json().get("detail", "") if response.content else ""
            raise RemoteError(response.status_code, str(detail))
        data: dict[str, Any] = response.json()
        return data

    def call(self, sender: str, to: str, path: str, payload: BaseModel | dict[str, Any]) -> Opened:
        return Courier(self.envelopes(sender), self.post).call(to, path, payload)

    def open_account(self, member: str, opening: AccountOpening) -> None:
        self.call("sim", member, "/v1/accounts", opening)

    def transfer(
        self, payment: Payment, payer: tuple[str, AccountRef], payee: tuple[str, AccountRef]
    ) -> None:
        """Post a payment as two ledger lines: a debit at the payer's bank and a credit at the payee's."""
        self.seq += 1
        (payer_member, payer_ref), (payee_member, payee_ref) = payer, payee
        assert payer_ref.account_number
        assert payee_ref.account_number
        debit = LedgerPosting(
            txn_id=f"d{self.seq}",
            account_number=payer_ref.account_number,
            direction="debit",
            payment=payment,
            counterparty=payee_ref,
        )
        credit = LedgerPosting(
            txn_id=f"c{self.seq}",
            account_number=payee_ref.account_number,
            direction="credit",
            payment=payment,
            counterparty=payer_ref,
        )
        self.call("sim", payer_member, "/v1/postings", {"postings": [debit.model_dump(mode="json")]})
        self.call("sim", payee_member, "/v1/postings", {"postings": [credit.model_dump(mode="json")]})

    def cash_out(self, member: str, account: str, payment: Payment, exit_detail: ExitDetail) -> None:
        self.seq += 1
        debit = LedgerPosting(
            txn_id=f"x{self.seq}",
            account_number=account,
            direction="debit",
            payment=payment,
            exit=exit_detail,
        )
        self.call("sim", member, "/v1/postings", {"postings": [debit.model_dump(mode="json")]})
