"""The bank's own accounts, postings and liens.

In a bank, these rows would come from the core banking system through an adapter, and liens would be placed there.
In the simulation the node's own ledger stands in for core banking, and it refuses any debit that would touch
money under a lien.
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import Engine, ForeignKey, Integer, String, Text, UniqueConstraint, func, inspect, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from ripple_core.messages import AccountOpening, AccountRef, ExitDetail, LedgerPosting, Notice, NoticeResponse
from ripple_core.tracing import Claim, Direction, Entry, Lien
from ripple_service.db import UtcDateTime


class LedgerConflict(ValueError):  # noqa: N818 - reads as the HTTP 409 it becomes
    """A posting the ledger cannot accept."""


class NodeBase(DeclarativeBase):
    pass


class Account(NodeBase):
    __tablename__ = "accounts"

    account_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    ifsc: Mapped[str] = mapped_column(String(11))
    vpa: Mapped[str | None] = mapped_column(String(320), unique=True)
    holder_name: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[str] = mapped_column(String(16))
    declared_profile: Mapped[str] = mapped_column(String(200))
    declared_annual_income: Mapped[int | None] = mapped_column(Integer)
    opening_balance: Mapped[int] = mapped_column(Integer)
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime())


class Posting(NodeBase):
    __tablename__ = "postings"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id: Mapped[str] = mapped_column(String(64), unique=True)
    account_number: Mapped[str] = mapped_column(ForeignKey("accounts.account_number"), index=True)
    direction: Mapped[str] = mapped_column(String(6))
    rail: Mapped[str] = mapped_column(String(8))
    reference: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    counterparty: Mapped[str | None] = mapped_column(Text)  # AccountRef as JSON
    exit: Mapped[str | None] = mapped_column(Text)  # ExitDetail as JSON

    def to_entry(self) -> Entry:
        return Entry(self.txn_id, self.at, Direction(self.direction), self.amount)

    def counterparty_ref(self) -> AccountRef | None:
        return AccountRef.model_validate_json(self.counterparty) if self.counterparty else None

    def exit_detail(self) -> ExitDetail | None:
        return ExitDetail.model_validate_json(self.exit) if self.exit else None


class LienRow(NodeBase):
    __tablename__ = "liens"
    __table_args__ = (UniqueConstraint("account_number", "claim"),)

    lien_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_number: Mapped[str] = mapped_column(ForeignKey("accounts.account_number"), index=True)
    claim: Mapped[str] = mapped_column(String(14))
    notice_id: Mapped[str] = mapped_column(String(64))
    amount: Mapped[int] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(String(40))
    placed_at: Mapped[datetime] = mapped_column(UtcDateTime())
    released_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    released_by: Mapped[str | None] = mapped_column(String(64))
    release_authority: Mapped[str | None] = mapped_column(
        String(200)
    )  # the police officer or court that ordered it
    release_order: Mapped[str | None] = mapped_column(String(64))  # the order's reference
    release_reason: Mapped[str | None] = mapped_column(Text)
    returned_to_victim: Mapped[bool] = mapped_column(default=False)


class HoldRow(NodeBase):
    """An RBI temporary debit hold the bank placed itself on a suspected mule credit (see `ripple_node.holds`).

    `amount` is the amount on hold; `whole_account` is the last-resort hold on every debit (Annex III para 6(ii)).
    The hold stops debits from `placed_at` until it is released or reaches `expires_at`.
    """

    __tablename__ = "debit_holds"

    hold_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_number: Mapped[str] = mapped_column(ForeignKey("accounts.account_number"), index=True)
    whole_account: Mapped[bool] = mapped_column(default=False)
    amount: Mapped[int] = mapped_column(Integer)
    credit_txns: Mapped[str] = mapped_column(Text)  # JSON list of the held credits' txn ids
    flag_keys: Mapped[str] = mapped_column(Text)  # JSON list of the flags behind the hold
    reasons: Mapped[str] = mapped_column(Text)  # JSON list of reason sentences
    account_level_reason: Mapped[str | None] = mapped_column(Text)
    contact: Mapped[str] = mapped_column(String(200))
    customer_notice: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    placed_by: Mapped[str] = mapped_column(String(64))
    placed_at: Mapped[datetime] = mapped_column(UtcDateTime())
    explanation_due: Mapped[datetime] = mapped_column(UtcDateTime())
    explanation_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    explanation: Mapped[str | None] = mapped_column(Text)
    decision_due: Mapped[datetime] = mapped_column(UtcDateTime())
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    decision: Mapped[str | None] = mapped_column(String(16))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    reported_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    instruction_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    instruction: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    released_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    release_reason: Mapped[str | None] = mapped_column(Text)
    mule_confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    str_draft: Mapped[str | None] = mapped_column(Text)  # JSON
    str_due: Mapped[datetime | None] = mapped_column(UtcDateTime())
    str_filed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    str_reference: Mapped[str | None] = mapped_column(String(64))

    def active_at(self, at: datetime) -> bool:
        if at < self.placed_at:
            return False
        end = self.released_at or self.expires_at
        return end is None or at < end


class NoticeRow(NodeBase):
    """Every notice received and the answer sent, so a repeated notice gets the same answer."""

    __tablename__ = "notices"

    notice_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ack_number: Mapped[str] = mapped_column(String(14), index=True)
    account_number: Mapped[str | None] = mapped_column(String(20), index=True)
    credit_txn: Mapped[str | None] = mapped_column(String(64))
    traced_amount: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime())
    notice: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)

    def stored_response(self) -> NoticeResponse:
        return NoticeResponse.model_validate_json(self.response)


def missing_columns(engine: Engine) -> list[str]:
    """Columns this version expects in tables that already exist; a database from an older version lacks some."""
    inspector = inspect(engine)
    missing = []
    for table in NodeBase.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in present]
    return missing


def open_account(session: Session, opening: AccountOpening) -> Account:
    if session.get(Account, opening.account_number) is not None:
        raise LedgerConflict(f"account {opening.account_number} already exists")
    if (
        opening.vpa is not None
        and session.scalar(select(Account).where(Account.vpa == opening.vpa)) is not None
    ):
        raise LedgerConflict(f"UPI ID {opening.vpa} already belongs to another account")
    account = Account(
        account_number=opening.account_number,
        ifsc=opening.ifsc,
        vpa=opening.vpa,
        holder_name=opening.holder_name,
        account_type=opening.account_type.value,
        declared_profile=opening.declared_profile,
        declared_annual_income=opening.declared_annual_income,
        opening_balance=opening.opening_balance,
        opened_at=opening.opened_at,
    )
    session.add(account)
    return account


def balance(session: Session, account: Account) -> int:
    def total(direction: str) -> int:
        query = select(func.coalesce(func.sum(Posting.amount), 0)).where(
            Posting.account_number == account.account_number, Posting.direction == direction
        )
        return int(session.scalar(query) or 0)

    return account.opening_balance + total("credit") - total("debit")


def held(session: Session, account_number: str) -> int:
    query = select(func.coalesce(func.sum(LienRow.amount), 0)).where(
        LienRow.account_number == account_number, LienRow.released_at.is_(None)
    )
    return int(session.scalar(query) or 0)


def post(session: Session, posting: LedgerPosting) -> Posting:
    account = session.get(Account, posting.account_number)
    if account is None:
        raise LedgerConflict(f"no account {posting.account_number}")
    if session.scalar(select(Posting).where(Posting.txn_id == posting.txn_id)) is not None:
        raise LedgerConflict(f"transaction {posting.txn_id} is already posted")
    if posting.payment.at < account.opened_at:
        raise LedgerConflict(f"transaction {posting.txn_id} is before the account was opened")
    if posting.direction == "debit":
        holds = [
            h
            for h in session.scalars(select(HoldRow).where(HoldRow.account_number == account.account_number))
            if h.active_at(posting.payment.at)
        ]
        if any(h.whole_account for h in holds):
            raise LedgerConflict(f"transaction {posting.txn_id}: every debit from this account is on hold")
        on_hold = held(session, account.account_number) + sum(h.amount for h in holds)
        available = balance(session, account) - on_hold
        if posting.payment.amount > available:
            raise LedgerConflict(
                f"transaction {posting.txn_id} is more than the balance not under a lien or a debit hold"
            )
    row = Posting(
        txn_id=posting.txn_id,
        account_number=posting.account_number,
        direction=posting.direction,
        rail=posting.payment.rail.value,
        reference=posting.payment.reference,
        amount=posting.payment.amount,
        at=posting.payment.at,
        counterparty=posting.counterparty.model_dump_json() if posting.counterparty else None,
        exit=posting.exit.model_dump_json() if posting.exit else None,
    )
    session.add(row)
    session.flush()
    return row


def find_account(session: Session, ref: AccountRef) -> Account | None:
    if ref.account_number is not None:
        account = session.get(Account, ref.account_number)
        return account if account is not None and account.ifsc == ref.ifsc else None
    return session.scalar(select(Account).where(Account.vpa == ref.vpa))


def postings(session: Session, account_number: str) -> list[Posting]:
    query = select(Posting).where(Posting.account_number == account_number).order_by(Posting.at, Posting.seq)
    return list(session.scalars(query))


def traced_in(session: Session, account_number: str) -> dict[str, dict[Claim, int]]:
    """Every victim's money that notices have traced into this account: credit txn -> claim -> paise."""
    rows = session.scalars(
        select(NoticeRow).where(NoticeRow.account_number == account_number, NoticeRow.credit_txn.is_not(None))
    )
    result: dict[str, dict[Claim, int]] = {}
    for row in rows:
        assert row.credit_txn is not None  # noqa: S101 - guaranteed by the query
        by_claim = result.setdefault(row.credit_txn, {})
        by_claim[row.ack_number] = max(by_claim.get(row.ack_number, 0), row.traced_amount)
    return result


def liens(session: Session, account_number: str) -> list[Lien]:
    rows = session.scalars(
        select(LienRow).where(LienRow.account_number == account_number, LienRow.released_at.is_(None))
    )
    return [Lien(r.placed_at, r.claim, r.amount) for r in rows]


def place_lien(session: Session, account: Account, notice: Notice, amount: int, now: datetime) -> LienRow:
    """A lien on the traced amount only, never the whole account (SOP 9.1; Bombay and Allahabad High Courts)."""
    existing = session.scalar(
        select(LienRow).where(
            LienRow.account_number == account.account_number, LienRow.claim == notice.ack_number
        )
    )
    if existing is not None:
        return existing
    row = LienRow(
        lien_id="L" + secrets.token_hex(8).upper(),
        account_number=account.account_number,
        claim=notice.ack_number,
        notice_id=notice.notice_id,
        amount=amount,
        basis=notice.legal_basis.value,
        placed_at=now,
        released_at=None,
    )
    session.add(row)
    session.flush()
    return row
