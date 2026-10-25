"""The PRD's demo story: a digital-arrest scam traced across six institutions.

A retired teacher sends Rs 8,00,000 by RTGS from Bank A to M1 at Bank B. Within nine minutes M1 splits it to M2
at Bank C, M3 at Bank D and a wallet; M2 takes Rs 2,00,000 out at two ATMs and sends Rs 1,00,000 to a crypto
exchange; M3, a shop with Rs 3,00,000 of its own money, pays a cement supplier, a phone shop and its assistant's
salary. The victim calls 1930 twelve minutes after paying.

`seed` posts the story to the network through any `Call`, so the same story runs in tests and on the live network.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel

from ripple_core.messages import (
    AccountOpening,
    AccountRef,
    Complaint,
    ExitDetail,
    ExitMode,
    LedgerPosting,
    Payment,
    Rail,
)
from ripple_core.money import rupees
from ripple_core.signing import Opened

Call = Callable[[str, str, str, BaseModel | dict[str, Any]], Opened]  # (sender, member, path, payload)


@dataclass(frozen=True)
class Party:
    key: str
    member: str
    holder: str
    ref: AccountRef
    opening_rupees: int
    profile: str = ""


@dataclass(frozen=True)
class Story:
    parties: dict[str, Party]
    victim_payment: Payment
    started_at: datetime

    def holder(self, account_number: str | None) -> str:
        for p in self.parties.values():
            if p.ref.account_number == account_number:
                return p.holder
        return account_number or "unknown"

    def complaint(self, ack_number: str, filed_at: datetime) -> Complaint:
        return Complaint(
            ack_number=ack_number,
            victim_name=self.parties["victim"].holder,
            payment=self.victim_payment,
            beneficiary=self.parties["m1"].ref,
            filed_at=filed_at,
        )


def parties(run: str) -> dict[str, Party]:
    """The story's accounts. `run` (6 digits) keeps account numbers and UPI IDs unique across runs."""

    def party(key: str,
        *, member: str, code: str, n: int, holder: str, opening: int, vpa: str | None = None,
              profile: str = "") -> Party:  # fmt: skip
        ref = AccountRef(ifsc=f"{code}0000001", account_number=f"{n}{run}{len(key):03d}", vpa=vpa)
        return Party(key, member, holder, ref, opening, profile)

    return {
        p.key: p
        for p in [
            party(
                "victim",
                member="bank-a",
                code="BKAA",
                n=1,
                holder="Retired teacher (victim)",
                opening=1_000_000,
            ),
            party(
                "ravi",
                member="bank-a",
                code="BKAA",
                n=2,
                holder="Ravi Traders (cement supplier)",
                opening=50_000,
            ),
            party(
                "m1",
                member="bank-b",
                code="BKBB",
                n=3,
                holder="M1 (mule)",
                opening=0,
                vpa=f"m1shop{run}@bkbb",
            ),
            party(
                "galaxy",
                member="bank-b",
                code="BKBB",
                n=4,
                holder="Galaxy Mobiles (phone shop)",
                opening=20_000,
                vpa=f"galaxy{run}@bkbb",
            ),
            party("m2", member="bank-c", code="BKCC", n=5, holder="M2 (mule)", opening=0),
            party(
                "assistant", member="bank-c", code="BKCC", n=6, holder="M3's shop assistant", opening=1_000
            ),
            party(
                "m3",
                member="bank-d",
                code="BKDD",
                n=7,
                holder="M3 General Store (mule)",
                opening=300_000,
                profile="small shop",
            ),
            party("wallet", member="wallet-w", code="WLTW", n=8, holder="Wallet W holder", opening=0),
            party("crypto", member="exchange-x", code="XCHX", n=9, holder="Exchange X customer", opening=0),
        ]
    }


def seed(call: Call, start: datetime, run: str) -> Story:
    """Open the accounts and post every payment of the story, starting at `start`."""
    ps = parties(run)
    for p in ps.values():
        assert p.ref.account_number is not None and p.ref.ifsc is not None  # noqa: PT018, S101 - built above
        opening = AccountOpening(
            account_number=p.ref.account_number,
            ifsc=p.ref.ifsc,
            holder_name=p.holder,
            vpa=p.ref.vpa,
            declared_profile=p.profile,
            opening_balance=rupees(p.opening_rupees),
            opened_at=start - timedelta(days=30),
        )
        call("sim", p.member, "/v1/accounts", opening)

    counter = iter(range(1, 100))

    def pay(rail: Rail, amount: int, minute: int) -> Payment:
        n = next(counter)
        reference = {
            Rail.RTGS: f"BKAAR{run}{n:011d}",
            Rail.NEFT: f"BKDDN{run}{n:05d}",
            Rail.INTERNAL: f"ATMW{run}{n:02d}",
        }.get(rail, f"{run}{n:06d}")
        return Payment(
            rail=rail, reference=reference, amount=rupees(amount), at=start + timedelta(minutes=minute)
        )

    def post(member: str, posting: LedgerPosting) -> None:
        call("sim", member, "/v1/postings", {"postings": [posting.model_dump(mode="json")]})

    def transfer(payment: Payment, payer: str, payee: str) -> None:
        a, b = ps[payer], ps[payee]
        assert a.ref.account_number and b.ref.account_number  # noqa: PT018, S101 - built above
        post(a.member, LedgerPosting(txn_id=f"D{payment.reference}", account_number=a.ref.account_number,
                                     direction="debit", payment=payment, counterparty=b.ref))  # fmt: skip
        post(b.member, LedgerPosting(txn_id=f"C{payment.reference}", account_number=b.ref.account_number,
                                     direction="credit", payment=payment, counterparty=a.ref))  # fmt: skip

    def atm(payer: str, amount: int, minute: int, atm_id: str, location: str) -> None:
        payment = pay(Rail.INTERNAL, amount, minute)
        p = ps[payer]
        assert p.ref.account_number  # noqa: S101 - built above
        post(p.member, LedgerPosting(
            txn_id=f"X{payment.reference}", account_number=p.ref.account_number, direction="debit",
            payment=payment, exit=ExitDetail(mode=ExitMode.ATM, reference=payment.reference, identifier=atm_id,
                                             location=location),
        ))  # fmt: skip

    victim_payment = pay(Rail.RTGS, 800_000, 0)
    transfer(victim_payment, "victim", "m1")
    transfer(pay(Rail.IMPS, 300_000, 2), "m1", "m2")
    transfer(pay(Rail.UPI, 250_000, 3), "m1", "m3")
    transfer(pay(Rail.IMPS, 150_000, 4), "m1", "wallet")
    atm("m2", 100_000, 5, "S1BW000101", "Ameerpet, Hyderabad")
    transfer(pay(Rail.NEFT, 200_000, 5), "m3", "ravi")
    transfer(pay(Rail.IMPS, 100_000, 6), "m2", "crypto")
    transfer(pay(Rail.UPI, 120_000, 6), "m3", "galaxy")
    atm("m2", 100_000, 7, "S1BW000245", "Secunderabad")
    transfer(pay(Rail.IMPS, 15_000, 8), "m3", "assistant")
    return Story(ps, victim_payment, start)
