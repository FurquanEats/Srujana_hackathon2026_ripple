"""Bank consortium: catch mule rings that cross banks without any bank sharing customer data.

Each member bank runs its own Ripple engine on the payments its own customers send or receive. When a bank alerts,
it reports the accounts involved to a shared hub, but only as keyed hashes (HMAC-SHA256 with a key the members hold
and the hub operator does not need), with a timestamp. When a bank later scores a payment, it hashes both accounts
and asks the hub whether another member flagged either recently. A match becomes a graph-layer reason; as
context, it cannot escalate a case on its own (see ripple.fusion), but it lifts payments that also look odd locally.

IBM AML account IDs carry the bank ("bank:account"), which lets ripple.consortium.evaluate measure how much each
bank gains from the joint view against working alone.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ripple.engine import Engine
from ripple.schema import Layer, Reason, ScoredTransaction, Transaction

SHARE_STRENGTH = 0.7


def bank_of(account: str) -> str:
    for sep in (":", "-"):
        if sep in account:
            return account.split(sep, 1)[0]
    return account


@dataclass
class Hub:
    """Holds only (keyed hash, reporting bank, time). It never sees an account number or an amount."""

    key: bytes
    window: timedelta = timedelta(days=3)
    flags: dict[str, list[tuple[str, datetime]]] = field(default_factory=dict)

    def token(self, account: str) -> str:
        return hmac.new(self.key, account.encode(), hashlib.sha256).hexdigest()[:24]

    def report(self, bank: str, account: str, ts: datetime) -> None:
        entries = self.flags.setdefault(self.token(account), [])
        entries.append((bank, ts))
        while entries and ts - entries[0][1] > self.window:
            entries.pop(0)

    def flagged_elsewhere(self, bank: str, account: str, ts: datetime) -> list[str]:
        return sorted({b for b, when in self.flags.get(self.token(account), []) if b != bank and ts - when <= self.window})


class Consortium:
    def __init__(self, banks: Iterable[str], pack: str = "ibm_aml", key: bytes = b"ripple-consortium-demo-key",
                 sharing: bool = True) -> None:
        self.hub = Hub(key)
        self.sharing = sharing
        self.engines: dict[str, Engine] = {}
        for bank in banks:
            engine = Engine(pack)
            engine.external = self._lookup(bank) if sharing else None
            self.engines[bank] = engine

    def _lookup(self, bank: str):
        def external(txn: Transaction) -> Reason | None:
            for account in (txn.src_account, txn.dst_account):
                # Includes the bank's own customer: another bank may have flagged a payment it received, which this
                # bank could not judge because it never saw the sender's other activity.
                others = self.hub.flagged_elsewhere(bank, account, txn.ts)
                if others:
                    return Reason(
                        layer=Layer.GRAPH,
                        code="consortium",
                        text=f"{account} was flagged in the last 3 days by {len(others)} other bank"
                        f"{'s' if len(others) > 1 else ''} in the consortium (shared as a keyed hash; no customer "
                        f"data exchanged)",
                        strength=SHARE_STRENGTH,
                        txn_ids=[txn.txn_id],
                    )
            return None

        return external

    def process(self, txn: Transaction) -> dict[str, ScoredTransaction]:
        """Scores the payment at every member bank whose customer sends or receives it."""
        results: dict[str, ScoredTransaction] = {}
        for bank in {bank_of(txn.src_account), bank_of(txn.dst_account)}:
            engine = self.engines.get(bank)
            if engine is None:
                continue
            scored, _ = engine.process(txn)
            results[bank] = scored
            if scored.is_alert and self.sharing and any(r.layer == Layer.DETECTOR for r in scored.reasons):
                for account in (txn.src_account, txn.dst_account):
                    self.hub.report(bank, account, txn.ts)
        return results
