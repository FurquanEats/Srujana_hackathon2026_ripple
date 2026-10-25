"""What the bank's own officers see: the notices the node answered, each with the account statement around it, and
the liens in force. These views read the node's database only; they never change it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ripple_core.messages import (
    AccountRef,
    Exit,
    ExitDetail,
    Notice,
    NoticeResponse,
    OnwardHop,
    Payment,
    Rail,
)
from ripple_core.tracing import trace_account
from ripple_node import ledger
from ripple_node.ledger import Account, LienRow, NoticeRow, Posting

STATEMENT_LEAD = timedelta(days=1)  # how far before the traced credit the statement starts


class View(BaseModel):
    model_config = ConfigDict(frozen=True)


class NoticeSummary(View):
    notice_id: str
    ack_number: str
    layer: int
    account_number: str | None
    holder_name: str | None
    received_at: datetime
    status: str
    reason: str | None
    traced_in: int
    held: int
    lien_id: str | None
    onward_count: int
    exit_count: int


class StatementLine(View):
    txn_id: str
    at: datetime
    direction: str
    rail: Rail
    reference: str
    amount: int
    counterparty: AccountRef | None
    exit: ExitDetail | None
    victim_money: dict[str, int]  # claim (NCRP acknowledgement) -> paise of victim money in this line


class NoticeDetail(View):
    summary: NoticeSummary
    credit: Payment
    legal_basis: str
    onward: tuple[OnwardHop, ...]
    exits: tuple[Exit, ...]
    statement: tuple[StatementLine, ...]


class LienView(View):
    lien_id: str
    account_number: str
    holder_name: str
    ack_number: str
    amount: int
    basis: str
    placed_at: datetime
    released_at: datetime | None


def _summary(row: NoticeRow, holders: dict[str, str]) -> NoticeSummary:
    notice = Notice.model_validate_json(row.notice)
    response = NoticeResponse.model_validate_json(row.response)
    return NoticeSummary(
        notice_id=row.notice_id,
        ack_number=row.ack_number,
        layer=notice.layer,
        account_number=row.account_number,
        holder_name=holders.get(row.account_number or ""),
        received_at=row.received_at,
        status=response.status,
        reason=response.reason,
        traced_in=response.traced_in if response.status == "matched" else notice.traced_amount,
        held=response.held_amount,
        lien_id=response.lien_id,
        onward_count=len(response.onward),
        exit_count=len(response.exits),
    )


def _holders(session: Session) -> dict[str, str]:
    return {a.account_number: a.holder_name for a in session.scalars(select(Account))}


def notices(session: Session) -> list[NoticeSummary]:
    holders = _holders(session)
    rows = session.scalars(
        select(NoticeRow).order_by(NoticeRow.received_at.desc(), NoticeRow.notice_id.desc())
    )
    return [_summary(r, holders) for r in rows]


def notice_detail(session: Session, notice_id: str, now: datetime) -> NoticeDetail | None:
    row = session.get(NoticeRow, notice_id)
    if row is None:
        return None
    notice = Notice.model_validate_json(row.notice)
    response = NoticeResponse.model_validate_json(row.response)
    summary = _summary(row, _holders(session))
    statement: tuple[StatementLine, ...] = ()
    account = session.get(Account, row.account_number) if row.account_number else None
    credit = (
        session.scalar(select(Posting).where(Posting.txn_id == row.credit_txn)) if row.credit_txn else None
    )
    if account is not None and credit is not None:
        statement = _statement(session, account, credit.at - STATEMENT_LEAD, now)
    return NoticeDetail(
        summary=summary,
        credit=notice.credit,
        legal_basis=notice.legal_basis.value,
        onward=response.onward,
        exits=response.exits,
        statement=statement,
    )


def _statement(
    session: Session, account: Account, start: datetime, now: datetime
) -> tuple[StatementLine, ...]:
    rows = ledger.postings(session, account.account_number)
    traced = ledger.traced_in(session, account.account_number)
    trace = trace_account(
        (r.to_entry() for r in rows),
        opening_balance=account.opening_balance,
        traced_in=traced,
        liens=ledger.liens(session, account.account_number),
        as_of=now,
    )
    carried = {d.txn_id: dict(d.carried) for d in trace.debits}
    lines = []
    for r in rows:
        if r.at < start or r.at > now:
            continue
        victim = dict(traced.get(r.txn_id, {})) if r.direction == "credit" else carried.get(r.txn_id, {})
        lines.append(
            StatementLine(
                txn_id=r.txn_id,
                at=r.at,
                direction=r.direction,
                rail=Rail(r.rail),
                reference=r.reference,
                amount=r.amount,
                counterparty=r.counterparty_ref(),
                exit=r.exit_detail(),
                victim_money=victim,
            )
        )
    return tuple(lines)


def liens(session: Session) -> list[LienView]:
    holders = _holders(session)
    rows = session.scalars(select(LienRow).order_by(LienRow.placed_at.desc()))
    return [
        LienView(
            lien_id=r.lien_id,
            account_number=r.account_number,
            holder_name=holders.get(r.account_number, ""),
            ack_number=r.claim,
            amount=r.amount,
            basis=r.basis,
            placed_at=r.placed_at,
            released_at=r.released_at,
        )
        for r in rows
    ]
