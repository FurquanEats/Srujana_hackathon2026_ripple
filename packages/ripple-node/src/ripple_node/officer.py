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
from ripple_service.db import append_audit

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
    release_authority: str | None = None
    release_order: str | None = None
    release_reason: str | None = None
    returned_to_victim: bool = False


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
            release_authority=r.release_authority,
            release_order=r.release_order,
            release_reason=r.release_reason,
            returned_to_victim=r.returned_to_victim,
        )
        for r in rows
    ]


def release_lien(
    session: Session,
    lien_id: str,
    *,
    now: datetime,
    actor: str,
    authority: str,
    order: str,
    reason: str,
    to_victim: bool,
) -> LienRow:
    """Lift a lien on a police or court order (SOP 11: interim custody under BNSS 106(3), or a court's order).

    The bank never lifts a CFCFRMS lien on its own; the order's authority and reference are kept with the lien
    and in the audit log. `to_victim` records that the money is returned to the victim rather than to the holder.
    """
    row = session.get(LienRow, lien_id)
    if row is None:
        raise ledger.LedgerConflict(f"no lien {lien_id} at this bank")
    if row.released_at is not None:
        raise ledger.LedgerConflict("this lien is already released")
    row.released_at = now
    row.released_by = actor
    row.release_authority = authority.strip()
    row.release_order = order.strip()
    row.release_reason = reason.strip()
    row.returned_to_victim = to_victim
    append_audit(session, now, actor, "lien.release", {
        "lien_id": lien_id, "account": row.account_number, "ack_number": row.claim, "amount": row.amount,
        "authority": row.release_authority, "order": row.release_order, "to_victim": to_victim,
    })  # fmt: skip
    return row


class AccountLine(View):
    txn_id: str
    at: datetime
    direction: str
    rail: Rail
    reference: str
    amount: int
    counterparty: AccountRef | None
    exit: ExitDetail | None


class AccountView(View):
    """Everything this bank knows about one of its accounts, for the officer's account page."""

    account_number: str
    ifsc: str
    vpa: str | None
    holder_name: str
    account_type: str
    declared_profile: str
    declared_annual_income: int | None
    opened_at: datetime
    balance: int
    liened: int
    on_hold: int
    available: int
    credits_30d: int
    debits_30d: int
    counterparties_30d: int
    statement: tuple[AccountLine, ...]
    notices: tuple[NoticeSummary, ...]
    liens: tuple[LienView, ...]


STATEMENT_ROWS = 60


def account_view(session: Session, account_number: str, now: datetime) -> AccountView | None:
    account = session.get(Account, account_number)
    if account is None:
        return None
    posts = ledger.postings(session, account_number)
    month = [p for p in posts if now - timedelta(days=30) <= p.at <= now]
    on_hold = sum(
        h.amount for h in session.scalars(select(ledger.HoldRow).where(ledger.HoldRow.account_number == account_number))
        if h.active_at(now) and not h.whole_account
    )  # fmt: skip
    balance = ledger.balance(session, account)
    liened = ledger.held(session, account_number)
    holders = _holders(session)
    return AccountView(
        account_number=account.account_number,
        ifsc=account.ifsc,
        vpa=account.vpa,
        holder_name=account.holder_name,
        account_type=account.account_type,
        declared_profile=account.declared_profile,
        declared_annual_income=account.declared_annual_income,
        opened_at=account.opened_at,
        balance=balance,
        liened=liened,
        on_hold=on_hold,
        available=max(balance - liened - on_hold, 0),
        credits_30d=sum(p.amount for p in month if p.direction == "credit"),
        debits_30d=sum(p.amount for p in month if p.direction == "debit"),
        counterparties_30d=len({p.counterparty for p in month if p.counterparty}),
        statement=tuple(
            AccountLine(
                txn_id=p.txn_id,
                at=p.at,
                direction=p.direction,
                rail=Rail(p.rail),
                reference=p.reference,
                amount=p.amount,
                counterparty=p.counterparty_ref(),
                exit=p.exit_detail(),
            )
            for p in reversed(posts[-STATEMENT_ROWS:])
        ),
        notices=tuple(
            _summary(r, holders)
            for r in session.scalars(select(NoticeRow).where(NoticeRow.account_number == account_number))
        ),
        liens=tuple(lien for lien in liens(session) if lien.account_number == account_number),
    )
