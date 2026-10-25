"""RBI's temporary debit hold: every path through its clocks, the notice, the STR draft and the ledger's refusal to
let held money leave. No hold may outlive its deadline."""

from __future__ import annotations

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
    Payment,
    Rail,
)
from ripple_core.money import rupees
from ripple_node import holds, ledger, monitoring
from ripple_node.holds import HoldError
from ripple_node.ledger import LedgerConflict, NodeBase
from ripple_service.db import init_db, make_engine, transaction, verify_audit

T0 = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
MULE = "200000000001"
PAYER = AccountRef(ifsc="BKAA0000001", account_number="100000000001")
ELSEWHERE = AccountRef(ifsc="BKCC0000001", account_number="300000000001")
DAY = timedelta(days=1)


def posting(txn: str, direction: str, rupee: int, minute: int, *, ref: str) -> LedgerPosting:
    payment = Payment(rail=Rail.IMPS, reference=ref, amount=rupees(rupee), at=T0 + timedelta(minutes=minute))
    return LedgerPosting(
        txn_id=txn,
        account_number=MULE,
        direction=direction,
        payment=payment,
        counterparty=PAYER if direction == "credit" else ELSEWHERE,
    )


@pytest.fixture
def factory() -> sessionmaker[Session]:
    """A student account that receives Rs 2,50,000 and sends Rs 1,00,000 on within two minutes."""
    factory = init_db(make_engine(None), NodeBase.metadata)
    with transaction(factory) as s:
        ledger.open_account(
            s,
            AccountOpening(
                account_number=MULE,
                ifsc="BKBB0000001",
                holder_name="Rohan Verma",
                declared_profile="individual; student; declared annual income Rs 0",
                declared_annual_income=0,
                opened_at=T0 - timedelta(days=200),
            ),
        )
        ledger.post(s, posting("c1", "credit", 2_50_000, 0, ref="111111111111"))
        ledger.post(s, posting("d1", "debit", 2_20_000, 2, ref="222222222222"))
        monitoring.rescan(s, [MULE], T0 + timedelta(minutes=3))
    return factory


def open_flags(s: Session) -> list[str]:
    [case] = monitoring.cases(s, T0)
    return [f.key for f in case.flags]


def place(s: Session, now: datetime, **kw: object) -> ledger.HoldRow:
    return holds.place(
        s, now=now, actor="frm-1", bank_name="Bank B", account_number=MULE, flag_keys=open_flags(s),
        contact="Fraud Risk desk, Bank B, 1800 000 0000", **kw,  # type: ignore[arg-type]
    )  # fmt: skip


def test_the_case_shows_every_rule_with_its_reason(factory: sessionmaker[Session]) -> None:
    with transaction(factory) as s:
        [case] = monitoring.cases(s, T0)
    # unused for 200 days, then Rs 2,50,000 for a student who declared no income, gone in two minutes
    assert set(case.rules) == {"pass_through", "out_of_profile", "dormant_then_busy"}
    assert case.priority == "high"
    assert all(f.reason for f in case.flags)


def test_a_hold_covers_the_flagged_credit_capped_at_what_is_left(factory: sessionmaker[Session]) -> None:
    now = T0 + timedelta(minutes=9)
    with transaction(factory) as s:
        row = place(s, now)
        view = holds.view(s, row, now)
    assert row.amount == rupees(30_000)  # Rs 2,50,000 flagged, Rs 30,000 still in the account
    assert view.status == "awaiting_explanation"
    assert "debits of ₹30,000 from your account ending 0001" in view.customer_notice
    assert "by 09 November 2026" in view.customer_notice  # 20 days to explain
    assert "Contact: Fraud Risk desk, Bank B" in view.customer_notice
    assert [d.state for d in view.deadlines[:3]] == ["met", "open", "open"]


def test_held_money_cannot_leave_but_the_rest_can(factory: sessionmaker[Session]) -> None:
    with transaction(factory) as s:
        place(s, T0 + timedelta(minutes=9))
        ledger.post(s, posting("c2", "credit", 5_000, 20, ref="333333333333"))
        ledger.post(s, posting("d2", "debit", 5_000, 21, ref="444444444444"))  # the new money is free
        with pytest.raises(LedgerConflict, match="debit hold"):
            ledger.post(s, posting("d3", "debit", 1, 22, ref="555555555555"))


def test_a_whole_account_hold_needs_a_written_reason_and_stops_every_debit(
    factory: sessionmaker[Session],
) -> None:
    with transaction(factory) as s:
        with pytest.raises(HoldError, match="last resort"):
            place(s, T0 + timedelta(minutes=9), whole_account=True, account_level_reason="suspicious")
        place(s, T0 + timedelta(minutes=9), whole_account=True,
              account_level_reason="The holder is a student who moved Rs 2.2 lakh on in two minutes.")  # fmt: skip
        with pytest.raises(LedgerConflict, match="every debit"):
            ledger.post(s, posting("d2", "debit", 1, 20, ref="444444444444"))


def test_explained_and_released(factory: sessionmaker[Session]) -> None:
    now = T0 + timedelta(minutes=9)
    with transaction(factory) as s:
        row = place(s, now)
        holds.record_explanation(
            s, row.hold_id, now=now + 5 * DAY, actor="frm-1", summary="Fees refund from college"
        )
        assert row.decision_due == now + 15 * DAY  # 10 days from the explanation
        holds.decide(
            s, row.hold_id, now=now + 8 * DAY, actor="frm-1", decision="release", reason="Refund letter"
        )
        view = holds.view(s, row, now + 8 * DAY)
    assert view.status == "released"
    assert view.compliance_breach is None
    assert "satisfied" in (view.release_reason or "")


def test_no_explanation_then_reported_then_released_on_the_31st_day(factory: sessionmaker[Session]) -> None:
    now = T0 + timedelta(minutes=9)
    with transaction(factory) as s:
        row = place(s, now)
        with pytest.raises(HoldError, match="has until"):
            holds.decide(s, row.hold_id, now=now + 10 * DAY, actor="frm-1", decision="report", reason="x")
        with pytest.raises(HoldError, match="20 days to explain ended"):
            holds.record_explanation(s, row.hold_id, now=now + 21 * DAY, actor="frm-1", summary="late")
        holds.decide(s, row.hold_id, now=now + 30 * DAY, actor="frm-1", decision="report", reason="No reply")
        assert row.expires_at == now + 60 * DAY  # the 31st day from the report, inside the 60-day cap
        assert holds.view(s, row, now + 59 * DAY).status == "reported_to_police"
        holds.sweep(s, now + 60 * DAY)
        view = holds.view(s, row, now + 60 * DAY)
    assert view.status == "released"
    assert view.released_at == now + 60 * DAY
    assert "31st day" in (view.release_reason or "")


def test_an_early_report_is_released_30_days_after_it(factory: sessionmaker[Session]) -> None:
    now = T0 + timedelta(minutes=9)
    with transaction(factory) as s:
        row = place(s, now)
        holds.record_explanation(
            s, row.hold_id, now=now + 2 * DAY, actor="frm-1", summary="Gift from an uncle"
        )
        holds.decide(s, row.hold_id, now=now + 4 * DAY, actor="frm-1", decision="report", reason="No proof")
    assert row.expires_at == now + 34 * DAY


def test_a_missed_decision_is_a_breach_and_the_60_day_cap_still_releases(
    factory: sessionmaker[Session],
) -> None:
    now = T0 + timedelta(minutes=9)
    with transaction(factory) as s:
        row = place(s, now)
        assert "Missed: bank decision" in (holds.view(s, row, now + 31 * DAY).compliance_breach or "")
        [released] = holds.sweep(s, now + 61 * DAY)
        assert released.released_at == now + 60 * DAY
        assert "60-day maximum" in (released.release_reason or "")
        ledger.post(
            s, posting("d2", "debit", 30_000, 60 * 24 * 61, ref="444444444444")
        )  # free to leave again


def test_police_instructions(factory: sessionmaker[Session]) -> None:
    now = T0 + timedelta(minutes=9)
    with transaction(factory) as s:
        row = place(s, now)
        with pytest.raises(HoldError, match="only a hold reported"):
            holds.record_instruction(
                s, row.hold_id, now=now, actor="frm-1", instruction="continue", authority="PS"
            )
        holds.decide(s, row.hold_id, now=now + 21 * DAY, actor="frm-1", decision="report", reason="No reply")
        holds.record_instruction(s, row.hold_id, now=now + 25 * DAY, actor="frm-1", instruction="continue",
                                 authority="Cyber Crime PS Hyderabad, FIR 112/2026")  # fmt: skip
        assert row.expires_at is None
        assert holds.sweep(s, now + 90 * DAY) == []  # the police instruction governs now
        assert holds.view(s, row, now + 90 * DAY).status == "held_on_police_instruction"


def test_a_confirmed_mule_needs_an_str_within_7_working_days(factory: sessionmaker[Session]) -> None:
    now = T0 + timedelta(minutes=9)  # a Tuesday
    with transaction(factory) as s:
        row = place(s, now)
        holds.confirm_mule(s, row.hold_id, now=now, actor="frm-1", grounds="Pass-through of a reported victim's money",
                           bank_name="Bank B", bank_code="BKBB")  # fmt: skip
        assert row.str_due == now + 9 * DAY  # 7 working days, skipping the weekend
        view = holds.view(s, row, now + DAY)
        assert view.str_draft is not None
        assert view.str_draft["account"]["holder_name"] == "Rohan Verma"
        assert [t["txn_id"] for t in view.str_draft["transactions"]] == ["c1", "d1"]
        assert holds.view(s, row, now + 10 * DAY).compliance_breach is not None
        holds.record_str_filed(s, row.hold_id, now=now + 10 * DAY, actor="po-1", reference="FINNET-STR-0001")
        assert holds.view(s, row, now + 10 * DAY).compliance_breach is not None  # filed late stays on record
        assert verify_audit(s) is None


def test_nodal_accounts_are_outside_the_procedure() -> None:
    factory = init_db(make_engine(None), NodeBase.metadata)
    with transaction(factory) as s:
        ledger.open_account(s, AccountOpening(account_number=MULE, ifsc="BKBB0000001", holder_name="PA Nodal",
                                              account_type=AccountType.NODAL, opened_at=T0 - DAY))  # fmt: skip
        ledger.post(s, posting("c1", "credit", 2_50_000, 0, ref="111111111111"))
        ledger.post(s, LedgerPosting(
            txn_id="x1", account_number=MULE, direction="debit",
            payment=Payment(rail=Rail.INTERNAL, reference="ATM1", amount=rupees(2_40_000),
                            at=T0 + timedelta(minutes=1)),
            exit=ExitDetail(mode=ExitMode.ATM, reference="ATM1", identifier="S1BW000101"),
        ))  # fmt: skip
        monitoring.rescan(s, [MULE], T0 + timedelta(minutes=2))
        with pytest.raises(HoldError, match="outside RBI's mule hold procedure"):
            place(s, T0 + timedelta(minutes=3))


def test_dismissing_a_case_keeps_the_reason(factory: sessionmaker[Session]) -> None:
    with transaction(factory) as s:
        assert (
            monitoring.dismiss(s, MULE, actor="frm-1", reason="Scholarship paid out to the hostel", now=T0)
            == 3
        )
        assert monitoring.cases(s, T0) == []
        [closed] = monitoring.cases(s, T0, include_closed=True)
        assert closed.flags[0].dismissed_reason == "Scholarship paid out to the hostel"


def test_a_database_from_an_older_version_is_detected() -> None:
    from sqlalchemy import text  # noqa: PLC0415 - only this test builds a table by hand

    engine = make_engine(None)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts (account_number TEXT PRIMARY KEY)"))
    assert "accounts.declared_annual_income" in ledger.missing_columns(engine)
    assert ledger.missing_columns(make_engine(None)) == []
