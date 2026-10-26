"""Answer a CFCFRMS notice in one step: find the credit, trace the victim's money, lien what is left, and report
where the rest went (MHA SOP for NCRP-CFCFRMS, paras 6.1 g to k and 9.1).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ripple_core.messages import AccountType, Exit, Notice, NoticeResponse, OnwardHop, Payment, Rail
from ripple_core.tracing import LedgerError, trace_account
from ripple_node import ledger
from ripple_node.ledger import NoticeRow, Posting
from ripple_service.db import append_audit

log = logging.getLogger(__name__)


class TracingError(LedgerError):
    """The trace did not account for every traced rupee. The node refuses to answer rather than answer wrongly."""


def respond(session: Session, notice: Notice, now: datetime, actor: str) -> NoticeResponse:
    previous = session.get(NoticeRow, notice.notice_id)
    if previous is not None:
        return previous.stored_response()

    account = ledger.find_account(session, notice.beneficiary)
    if account is None:
        response = _not_found(notice, now, "no such account at this bank")
        return _record(
            session, notice, now=now, actor=actor, account_number=None, credit_txn=None, response=response
        )
    credit = session.scalar(
        select(Posting).where(
            Posting.account_number == account.account_number,
            Posting.direction == "credit",
            Posting.reference == notice.credit.reference,
            Posting.amount == notice.credit.amount,
        )
    )
    reason = None
    if credit is None:
        reason = "no credit with this reference and amount in the account"
    elif credit.at > now:
        reason = "the credit is dated after this bank's current time"
    if credit is None or reason is not None:
        response = _not_found(notice, now, reason or "")
        return _record(
            session,
            notice,
            now=now,
            actor=actor,
            account_number=account.account_number,
            credit_txn=None,
            response=response,
        )

    traced = ledger.traced_in(session, account.account_number)
    by_claim = traced.setdefault(credit.txn_id, {})
    by_claim[notice.ack_number] = max(by_claim.get(notice.ack_number, 0), notice.traced_amount)
    rows = ledger.postings(session, account.account_number)
    trace = trace_account(
        (r.to_entry() for r in rows),
        opening_balance=account.opening_balance,
        traced_in=traced,
        liens=ledger.liens(session, account.account_number),
        as_of=now,
    )

    held = trace.remaining.get(notice.ack_number, 0)
    lien_id = None
    if held:
        lien = ledger.place_lien(session, account, notice, held, now)
        lien_id, held = lien.lien_id, lien.amount

    by_txn = {r.txn_id: r for r in rows}
    onward: list[OnwardHop] = []
    exits: list[Exit] = []
    for debit in trace.debits:
        carried = debit.carried.get(notice.ack_number, 0)
        if not carried:
            continue
        row = by_txn[debit.txn_id]
        detail, to = row.exit_detail(), row.counterparty_ref()
        if detail is not None:
            exits.append(
                Exit(
                    mode=detail.mode,
                    reference=detail.reference,
                    at=row.at,
                    amount=row.amount,
                    traced_amount=carried,
                    identifier=detail.identifier,
                    location=detail.location,
                )
            )
        elif to is not None:
            payment = Payment(rail=Rail(row.rail), reference=row.reference, amount=row.amount, at=row.at)
            onward.append(OnwardHop(payment=payment, to=to, traced_amount=carried))

    response = NoticeResponse(
        notice_id=notice.notice_id,
        status="matched",
        traced_in=held + sum(h.traced_amount for h in onward) + sum(e.traced_amount for e in exits),
        account_type=AccountType(account.account_type),
        holder_name=account.holder_name,
        held_amount=held,
        lien_id=lien_id,
        onward=tuple(onward),
        exits=tuple(exits),
        responded_at=now,
    )
    if response.traced_in != notice.traced_amount:
        log.error("trace for notice %s does not add up; not answering", notice.notice_id)
        raise TracingError(
            f"notice {notice.notice_id}: traced amounts do not add up"
        )  # property-tested never to happen
    return _record(
        session,
        notice,
        now=now,
        actor=actor,
        account_number=account.account_number,
        credit_txn=credit.txn_id,
        response=response,
    )


def _not_found(notice: Notice, now: datetime, reason: str) -> NoticeResponse:
    return NoticeResponse(notice_id=notice.notice_id, status="not_found", reason=reason, responded_at=now)


def _record(
    session: Session,
    notice: Notice,
    *,
    now: datetime,
    actor: str,
    account_number: str | None,
    credit_txn: str | None,
    response: NoticeResponse,
) -> NoticeResponse:
    session.add(
        NoticeRow(
            notice_id=notice.notice_id,
            ack_number=notice.ack_number,
            account_number=account_number,
            credit_txn=credit_txn,
            traced_amount=notice.traced_amount,
            received_at=now,
            notice=notice.model_dump_json(),
            response=response.model_dump_json(),
        )
    )
    append_audit(
        session,
        now,
        actor,
        "notice_answered",
        {
            "notice_id": notice.notice_id,
            "ack_number": notice.ack_number,
            "status": response.status,
            "held": response.held_amount,
            "lien_id": response.lien_id,
        },
    )
    return response
