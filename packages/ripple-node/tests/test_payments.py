"""The payment check: a coached transfer gets a cooling hold, a DPIP-reported payee gets hold and call, and an
ordinary payment goes through."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from ripple_core.clock import IST
from ripple_core.messages import AccountOpening, AccountRef, LedgerPosting, Payment, Rail
from ripple_core.money import rupees
from ripple_node import ledger, payments
from ripple_node.ledger import LedgerConflict, NodeBase
from ripple_service.db import init_db, make_engine, transaction

T0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
PENSIONER = "500000000001"
FD = AccountRef(ifsc="BKAA0000001", account_number="500000000099")
GROCER = AccountRef(ifsc="BKCC0000001", account_number="300000000001")
SAFE_ACCOUNT = AccountRef(ifsc="BKBB0000001", account_number="200000000077")


def line(n: int, direction: str, rupee: int, at: datetime, ref: AccountRef) -> LedgerPosting:
    payment = Payment(rail=Rail.IMPS, reference=f"{n:012d}", amount=rupees(rupee), at=at)
    return LedgerPosting(txn_id=f"t{n}", account_number=PENSIONER, direction=direction, payment=payment,
                         counterparty=ref)  # fmt: skip


@pytest.fixture
def factory() -> sessionmaker[Session]:
    """A pensioner who pays a grocer about Rs 3,000 a week, then breaks an Rs 8 lakh fixed deposit."""
    factory = init_db(make_engine(None), NodeBase.metadata)
    with transaction(factory) as s:
        ledger.open_account(s, AccountOpening(
            account_number=PENSIONER, ifsc="BKAA0000001", holder_name="Sudha Raman",
            declared_profile="individual; retired teacher; pension Rs 4,20,000 a year",
            declared_annual_income=rupees(4_20_000), opening_balance=rupees(60_000),
            opened_at=T0 - timedelta(days=3000),
        ))  # fmt: skip
        for week in range(10):
            ledger.post(s, line(week, "debit", 3_000, T0 - timedelta(days=70 - 7 * week), GROCER))
        ledger.post(s, line(99, "credit", 8_00_000, T0 - timedelta(hours=5), FD))
    return factory


def test_a_coached_transfer_of_most_of_a_broken_fd_gets_a_cooling_hold(
    factory: sessionmaker[Session],
) -> None:
    with factory() as s:
        result = payments.check(s, sender_account=PENSIONER, payee=SAFE_ACCOUNT, amount=rupees(7_50_000),
                                now=T0, dpip_level="none", dpip_reasons=())  # fmt: skip
    assert result.decision == "cooling_hold"
    assert result.cooling_minutes == payments.COOLING_MINUTES
    texts = " ".join(r.text for r in result.reasons)
    assert "never paid this payee" in texts
    assert "250 times" in texts
    assert "94%" in texts


def test_a_reported_payee_means_hold_and_call(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        result = payments.check(s, sender_account=PENSIONER, payee=SAFE_ACCOUNT, amount=rupees(5_000), now=T0,
                                dpip_level="very_high", dpip_reasons=("On the suspect registry.",))  # fmt: skip
    assert result.decision == "hold_and_call"
    assert result.reasons[0].source == "dpip"


def test_an_ordinary_payment_goes_through(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        result = payments.check(s, sender_account=PENSIONER, payee=GROCER, amount=rupees(3_200), now=T0,
                                dpip_level="none", dpip_reasons=())  # fmt: skip
        assert result.decision == "allow"
        assert result.reasons == ()
        with pytest.raises(LedgerConflict):
            payments.check(s, sender_account="999999999999", payee=GROCER, amount=1, now=T0,
                           dpip_level="none", dpip_reasons=())  # fmt: skip
