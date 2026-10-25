from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from ripple_core.clock import IST
from ripple_core.messages import (
    AccountOpening,
    AccountRef,
    AccountType,
    ExitDetail,
    ExitMode,
    LedgerPosting,
    Notice,
    Payment,
    Rail,
)
from ripple_core.money import rupees
from ripple_node import ledger, responder
from ripple_node.ledger import LedgerConflict, NodeBase
from ripple_service.db import init_db, make_engine, transaction

T0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
MULE = AccountRef(ifsc="BKBB0000001", account_number="200000000001", vpa="mule@bkbb")
PAYER = AccountRef(ifsc="BKAA0000001", account_number="100000000001")


@pytest.fixture
def factory() -> sessionmaker[Session]:
    factory = init_db(make_engine(None), NodeBase.metadata)
    with transaction(factory) as s:
        ledger.open_account(
            s,
            AccountOpening(
                account_number="200000000001",
                ifsc="BKBB0000001",
                holder_name="Mule",
                vpa="mule@bkbb",
                opened_at=T0 - timedelta(days=1),
            ),
        )
    return factory


def credit(txn: str, ref: str, amount: int, minute: int) -> LedgerPosting:
    return LedgerPosting(
        txn_id=txn,
        account_number="200000000001",
        direction="credit",
        payment=Payment(
            rail=Rail.IMPS, reference=ref, amount=rupees(amount), at=T0 + timedelta(minutes=minute)
        ),
        counterparty=PAYER,
    )


def notice(
    ref: str,
    amount: int,
    traced: int,
    *,
    beneficiary: AccountRef = MULE,
    nid: str = "n-000001",
    ack: str = "31234567890123",
) -> Notice:
    return Notice(
        notice_id=nid,
        ack_number=ack,
        layer=1,
        credit=Payment(rail=Rail.IMPS, reference=ref, amount=rupees(amount), at=T0),
        beneficiary=beneficiary,
        traced_amount=rupees(traced),
        issued_at=T0 + timedelta(hours=1),
    )


def test_postings_are_checked(factory: sessionmaker[Session]) -> None:
    with transaction(factory) as s:
        ledger.post(s, credit("c1", "111111111111", 1_000, 0))
        with pytest.raises(LedgerConflict, match="already posted"):
            ledger.post(s, credit("c1", "111111111111", 1_000, 0))
        with pytest.raises(LedgerConflict, match="no account"):
            ledger.post(s, credit("c2", "111111111112", 1, 0).model_copy(update={"account_number": "999999"}))
        with pytest.raises(LedgerConflict, match="before the account was opened"):
            ledger.post(s, credit("c3", "111111111113", 1, -60 * 48))
        with pytest.raises(LedgerConflict, match="already exists"):
            ledger.open_account(
                s,
                AccountOpening(
                    account_number="200000000001", ifsc="BKBB0000001", holder_name="Again", opened_at=T0
                ),
            )
        debit = LedgerPosting(
            txn_id="d1",
            account_number="200000000001",
            direction="debit",
            payment=Payment(
                rail=Rail.INTERNAL, reference="ATM1", amount=rupees(1_001), at=T0 + timedelta(minutes=1)
            ),
            exit=ExitDetail(mode=ExitMode.ATM, reference="ATM1", identifier="S1BW1"),
        )
        with pytest.raises(LedgerConflict, match="more than the balance"):
            ledger.post(s, debit)


def test_notice_for_unknown_account_or_credit_is_not_found(factory: sessionmaker[Session]) -> None:
    with transaction(factory) as s:
        ledger.post(s, credit("c1", "111111111111", 1_000, 0))
        stranger = AccountRef(ifsc="BKBB0000009", account_number="200000000009")
        a = responder.respond(
            s, notice("111111111111", 1_000, 1_000, beneficiary=stranger, nid="n-000001"), T0, "cfcfrms"
        )
        b = responder.respond(s, notice("222222222222", 1_000, 1_000, nid="n-000002"), T0, "cfcfrms")
        wrong_ifsc = AccountRef(ifsc="BKBB0000002", account_number="200000000001")
        c = responder.respond(
            s, notice("111111111111", 1_000, 1_000, beneficiary=wrong_ifsc, nid="n-000003"), T0, "cfcfrms"
        )
    assert (a.status, b.status, c.status) == ("not_found", "not_found", "not_found")
    assert a.reason == "no such account at this bank"
    assert b.reason is not None
    assert "reference" in b.reason


def test_a_notice_by_upi_id_is_matched_and_answered_once(factory: sessionmaker[Session]) -> None:
    with transaction(factory) as s:
        ledger.post(s, credit("c1", "111111111111", 1_000, 0))
        by_vpa = AccountRef(vpa="mule@bkbb")
        first = responder.respond(
            s, notice("111111111111", 1_000, 600, beneficiary=by_vpa), T0 + timedelta(hours=1), "cfcfrms"
        )
        again = responder.respond(
            s, notice("111111111111", 1_000, 600, beneficiary=by_vpa), T0 + timedelta(hours=2), "cfcfrms"
        )
        assert ledger.held(s, "200000000001") == rupees(600)
    assert first == again
    assert first.held_amount == rupees(600)
    assert first.account_type is AccountType.REGULAR


def test_two_victims_in_one_account_get_separate_liens(factory: sessionmaker[Session]) -> None:
    with transaction(factory) as s:
        ledger.post(s, credit("c1", "111111111111", 1_000, 0))
        ledger.post(s, credit("c2", "111111111112", 3_000, 1))
        a = responder.respond(
            s,
            notice("111111111111", 1_000, 1_000, nid="n-000001", ack="31111111111111"),
            T0 + timedelta(hours=1),
            "cfcfrms",
        )
        b = responder.respond(
            s,
            notice("111111111112", 3_000, 3_000, nid="n-000002", ack="32222222222222"),
            T0 + timedelta(hours=1),
            "cfcfrms",
        )
        assert ledger.held(s, "200000000001") == rupees(4_000)
    assert (a.held_amount, b.held_amount) == (rupees(1_000), rupees(3_000))
    assert a.lien_id != b.lien_id
