"""RBI's temporary debit hold on suspected money mule credits, with every deadline, the customer notice and the STR
draft (RBI draft KYC Amendment Directions 2026, Annex III: the SOP on suspected money mule accounts).

The bank places the hold itself, on the suspected credit's amount; a hold on the whole account is a last resort and
needs a written reason (Annex III para 6(ii)). The clocks, from the day the hold is placed:

- the customer is told at once, with the reasons, how to get the hold removed and the officer's contact (Step 2);
- the customer has 20 days to explain (Step 3);
- the bank decides within 10 days of an explanation, or within 30 days of the hold if none comes (Step 4);
- if it is not satisfied, it keeps the hold and reports to the police through NCRP-CFCFRMS (Step 4(b));
- the hold comes off on the 31st day from that report unless the police instruct otherwise (Steps 5 and 6),
  and no hold lasts more than 60 days without such an instruction.

We count the day of an event as day 1, so the 31st day from a report is 30 days after it. That keeps the longest
path (a report on day 30) inside the 60-day cap, as the SOP's note on maximum duration intends. When a mule is
confirmed, the bank must file an STR with FIU-IND within 7 working days of forming its suspicion (PML Rules,
rule 8(3)); a confirmed mule without a filed STR makes the bank non-compliant (Amendment Directions para 4(1)).

Nodal, pool, escrow and other special-purpose accounts are outside the SOP (Annex III para 2(2)), so the node
refuses holds on them. Every step goes to the append-only audit log, which keeps the records the SOP asks for
(para 7(3): five years from the hold, ten from account closure).
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ripple_core.clock import IST
from ripple_core.messages import AccountType
from ripple_core.money import fmt_inr
from ripple_node import ledger
from ripple_node.ledger import Account, HoldRow, LedgerConflict, NoticeRow
from ripple_node.monitoring import FlagRow
from ripple_service.db import AuditEntry, append_audit

EXPLAIN_WITHIN = timedelta(days=20)
DECIDE_AFTER_EXPLANATION = timedelta(days=10)
DECIDE_WITHOUT_EXPLANATION = timedelta(days=30)
RELEASE_AFTER_REPORT = timedelta(days=30)  # the 31st day, counting the day of the report as day 1
MAX_HOLD = timedelta(days=60)
STR_WORKING_DAYS = 7
MIN_ACCOUNT_LEVEL_REASON = 30  # characters: an account-level hold needs a real written reason
EXCLUDED_TYPES = frozenset({AccountType.NODAL.value, AccountType.POOL.value, AccountType.ESCROW.value})


class HoldError(LedgerConflict):
    """A hold step the SOP does not allow at this point."""


class View(BaseModel):
    model_config = ConfigDict(frozen=True)


class Deadline(View):
    name: str
    due: datetime
    met_at: datetime | None
    state: Literal["met", "open", "missed", "lapsed"]  # lapsed: the customer's own time ran out unused
    rule: str


class Note(View):
    at: datetime
    actor: str
    note: str


class HoldView(View):
    hold_id: str
    account_number: str
    holder_name: str
    whole_account: bool
    amount: int
    credit_txns: tuple[str, ...]
    reasons: tuple[str, ...]
    account_level_reason: str | None
    contact: str
    customer_notice: str
    status: str
    placed_by: str
    placed_at: datetime
    explanation_at: datetime | None
    explanation: str | None
    decision: str | None
    decision_reason: str | None
    reported_at: datetime | None
    instruction: str | None
    expires_at: datetime | None
    released_at: datetime | None
    release_reason: str | None
    mule_confirmed_at: datetime | None
    str_due: datetime | None
    str_filed_at: datetime | None
    str_reference: str | None
    str_draft: dict[str, Any] | None
    compliance_breach: str | None
    next_deadline: datetime | None
    deadlines: tuple[Deadline, ...]
    notes: tuple[Note, ...] = ()


def _when(at: datetime) -> str:
    return at.astimezone(IST).strftime("%d %B %Y")


def _get(session: Session, hold_id: str) -> HoldRow:
    row = session.get(HoldRow, hold_id)
    if row is None:
        raise HoldError(f"no hold {hold_id} at this bank")
    return row


def _event(session: Session, row: HoldRow, now: datetime, actor: str, action: str, **extra: Any) -> None:
    append_audit(
        session,
        now,
        actor,
        f"hold.{action}",
        {"hold_id": row.hold_id, "account": row.account_number, "status": row.status, **extra},
    )


def sweep(session: Session, now: datetime) -> list[HoldRow]:
    """Release every hold whose deadline has passed, at the deadline, and record it. Run before every hold read."""
    released = []
    for row in session.scalars(
        select(HoldRow).where(HoldRow.released_at.is_(None), HoldRow.expires_at <= now)
    ):
        assert row.expires_at is not None  # noqa: S101 - guaranteed by the query
        row.released_at = row.expires_at
        if row.reported_at is not None:
            row.release_reason = (
                "No instruction from the police by the 31st day from the report (Annex III Step 6)."
            )
        else:
            row.release_reason = (
                "The 60-day maximum for a temporary debit hold was reached (Annex III, Step 6 note)."
            )
        row.status = "released"
        _event(session, row, row.expires_at, "ripple", "release_at_deadline", reason=row.release_reason)
        released.append(row)
    return released


def place(
    session: Session,
    *,
    now: datetime,
    actor: str,
    bank_name: str,
    account_number: str,
    flag_keys: Sequence[str],
    contact: str,
    whole_account: bool = False,
    account_level_reason: str | None = None,
) -> HoldRow:
    """Place a temporary debit hold on the flagged credits' amount (or, as a last resort, the whole account)."""
    sweep(session, now)
    account = session.get(Account, account_number)
    if account is None:
        raise HoldError(f"no account {account_number}")
    if account.account_type in EXCLUDED_TYPES:
        raise HoldError(
            f"a {account.account_type} account is outside RBI's mule hold procedure (Annex III para 2(2)); "
            "use a CFCFRMS lien on the disputed amount instead"
        )
    if any(
        h.active_at(now)
        for h in session.scalars(select(HoldRow).where(HoldRow.account_number == account_number))
    ):
        raise HoldError("this account already has a temporary debit hold in force")
    flags = [session.get(FlagRow, k) for k in dict.fromkeys(flag_keys)]
    if not flags or any(f is None or f.account_number != account_number or f.status != "open" for f in flags):
        raise HoldError("name at least one open flag on this account")
    reasons = [f.reason for f in flags if f is not None]
    credit_ids = list(dict.fromkeys(t for f in flags if f is not None for t in json.loads(f.credit_txns)))
    rows = {p.txn_id: p for p in ledger.postings(session, account_number)}
    flagged = sum(rows[t].amount for t in credit_ids if t in rows and rows[t].direction == "credit")
    if whole_account:
        if not account_level_reason or len(account_level_reason.strip()) < MIN_ACCOUNT_LEVEL_REASON:
            raise HoldError(
                "a hold on the whole account is a last resort (Annex III para 6(ii)); write why holding the "
                f"credits alone is not enough, in at least {MIN_ACCOUNT_LEVEL_REASON} characters"
            )
        amount = 0
    else:
        available = ledger.balance(session, account) - ledger.held(session, account_number)
        amount = min(flagged, max(available, 0))
        if amount <= 0:
            raise HoldError(
                "the flagged money has already left the account, so there is nothing to hold on these credits"
            )
    row = HoldRow(
        hold_id="H" + secrets.token_hex(8).upper(),
        account_number=account_number,
        whole_account=whole_account,
        amount=amount,
        credit_txns=json.dumps(credit_ids),
        flag_keys=json.dumps([f.key for f in flags if f is not None]),
        reasons=json.dumps(reasons),
        account_level_reason=account_level_reason.strip() if whole_account and account_level_reason else None,
        contact=contact,
        customer_notice="",
        status="awaiting_explanation",
        placed_by=actor,
        placed_at=now,
        explanation_due=now + EXPLAIN_WITHIN,
        decision_due=now + DECIDE_WITHOUT_EXPLANATION,
        expires_at=now + MAX_HOLD,
    )
    row.customer_notice = customer_notice(row, account, bank_name)
    session.add(row)
    for f in flags:
        if f is not None:
            f.status = "held"
    session.flush()
    _event(session, row, now, actor, "place", amount=amount, whole_account=whole_account, credits=credit_ids)
    return row


def customer_notice(row: HoldRow, account: Account, bank_name: str) -> str:
    """The notice the bank sends at once: reasons, how to get the hold removed, and the officer (Step 2).

    It never names a victim or a complainant."""
    what = (
        "all debits from your account"
        if row.whole_account
        else f"debits of {fmt_inr(row.amount)} from your account"
    )
    reasons = " ".join(json.loads(row.reasons))
    return (
        f"Dear {account.holder_name},\n\n"
        f"{bank_name} has placed a temporary hold on {what} ending {account.account_number[-4:]}, from "
        f"{_when(row.placed_at)}. The bank has done this under the Reserve Bank of India's directions on suspected "
        f"money mule accounts, because of these transactions: {reasons}\n\n"
        "You can still receive money, and you can use any balance that is not on hold.\n\n"
        f"To have the hold removed, send the bank an explanation of these transactions, with any documents that "
        f"support it, such as invoices, agreements or salary slips, by {_when(row.explanation_due)}. The bank will "
        f"decide within 10 days of receiving your explanation. If no explanation reaches the bank, it will decide "
        f"by {_when(row.decision_due)}, and it may then report the transactions to the police through the National "
        "Cybercrime Reporting Portal.\n\n"
        f"Contact: {row.contact}"
    )


def record_explanation(session: Session, hold_id: str, *, now: datetime, actor: str, summary: str) -> HoldRow:
    sweep(session, now)
    row = _get(session, hold_id)
    if row.status != "awaiting_explanation":
        raise HoldError(f"this hold is {row.status.replace('_', ' ')}, so an explanation cannot be recorded")
    if now > row.explanation_due:
        raise HoldError(
            f"the 20 days to explain ended on {_when(row.explanation_due)}; the bank must now decide without one"
        )
    if not summary.strip():
        raise HoldError("record what the customer explained")
    row.explanation_at = now
    row.explanation = summary.strip()
    row.decision_due = now + DECIDE_AFTER_EXPLANATION
    row.status = "explanation_received"
    _event(session, row, now, actor, "explanation", decision_due=row.decision_due.isoformat())
    return row


def decide(
    session: Session,
    hold_id: str,
    *,
    now: datetime,
    actor: str,
    decision: Literal["release", "report"],
    reason: str,
) -> HoldRow:
    """Release the hold, or keep it and report to the police through NCRP-CFCFRMS (Step 4)."""
    sweep(session, now)
    row = _get(session, hold_id)
    if row.status not in {"awaiting_explanation", "explanation_received"}:
        raise HoldError(f"this hold is {row.status.replace('_', ' ')}, so there is no decision to take")
    if decision == "report" and row.status == "awaiting_explanation" and now <= row.explanation_due:
        raise HoldError(
            f"the customer has until {_when(row.explanation_due)} to explain; report only after an explanation "
            "or once that time has run out"
        )
    if not reason.strip():
        raise HoldError("write the reason for the decision")
    row.decided_at = now
    row.decision = decision
    row.decision_reason = reason.strip()
    if decision == "release":
        row.status = "released"
        row.released_at = now
        row.release_reason = "The bank was satisfied with the explanation (Annex III Step 4(a))."
    else:
        row.status = "reported_to_police"
        row.reported_at = now
        assert row.expires_at is not None  # noqa: S101 - set when placed
        row.expires_at = min(now + RELEASE_AFTER_REPORT, row.placed_at + MAX_HOLD)
    _event(session, row, now, actor, f"decide.{decision}", reason=row.decision_reason)
    return row


def record_instruction(
    session: Session,
    hold_id: str,
    *,
    now: datetime,
    actor: str,
    instruction: Literal["release", "continue"],
    authority: str,
) -> HoldRow:
    """The police authority's instruction on a reported hold, which the bank follows and tells the customer (Step 5)."""
    sweep(session, now)
    row = _get(session, hold_id)
    if row.status != "reported_to_police":
        raise HoldError("only a hold reported to the police can take a police instruction")
    if not authority.strip():
        raise HoldError("name the police authority and its reference")
    row.instruction_at = now
    row.instruction = f"{instruction}: {authority.strip()}"
    if instruction == "release":
        row.status = "released"
        row.released_at = now
        row.release_reason = f"Released on the instruction of {authority.strip()} (Annex III Step 5)."
    else:
        row.status = "held_on_police_instruction"
        row.expires_at = None  # the police instruction now governs the hold, not the 60-day cap
    _event(session, row, now, actor, f"instruction.{instruction}", authority=authority.strip())
    return row


def add_working_days(start: datetime, days: int) -> datetime:
    """Working days skip Saturdays and Sundays. Bank holidays vary by State and are not modelled."""
    at = start
    while days:
        at += timedelta(days=1)
        if at.astimezone(IST).weekday() < 5:
            days -= 1
    return at


def confirm_mule(
    session: Session, hold_id: str, *, now: datetime, actor: str, grounds: str, bank_name: str, bank_code: str
) -> HoldRow:
    """Record that the bank has formed its suspicion that the account is a mule, and draft the STR for FIU-IND."""
    sweep(session, now)
    row = _get(session, hold_id)
    if row.mule_confirmed_at is not None:
        raise HoldError("this account is already confirmed as a mule")
    if not grounds.strip():
        raise HoldError("write the grounds of suspicion")
    account = session.get(Account, row.account_number)
    assert account is not None  # noqa: S101 - a hold always has its account
    row.mule_confirmed_at = now
    row.str_due = add_working_days(now, STR_WORKING_DAYS)
    row.str_draft = json.dumps(
        str_draft(session, row, account, grounds=grounds.strip(), bank_name=bank_name, bank_code=bank_code)
    )
    _event(session, row, now, actor, "confirm_mule", str_due=row.str_due.isoformat())
    return row


def str_draft(
    session: Session, row: HoldRow, account: Account, *, grounds: str, bank_name: str, bank_code: str
) -> dict[str, Any]:
    """The facts an STR needs, for the principal officer to check and file on FINnet. Ripple never files it."""
    postings = ledger.postings(session, account.account_number)
    window_start = row.placed_at - timedelta(days=30)
    noticed = session.scalars(select(NoticeRow).where(NoticeRow.account_number == account.account_number))
    acks = sorted({n.ack_number for n in noticed})
    return {
        "report_type": "STR",
        "reporting_entity": {"name": bank_name, "bank_code": bank_code},
        "branch_ifsc": account.ifsc,
        "account": {
            "number": account.account_number,
            "type": account.account_type,
            "holder_name": account.holder_name,
            "declared_profile": account.declared_profile,
            "declared_annual_income": account.declared_annual_income,
            "opened_at": account.opened_at.isoformat(),
        },
        "suspicion_formed_at": (row.mule_confirmed_at or row.placed_at).isoformat(),
        "due_by": row.str_due.isoformat() if row.str_due else None,
        "grounds_of_suspicion": [*json.loads(row.reasons), grounds],
        "linked_ncrp_acknowledgements": acks,
        "temporary_debit_hold": {
            "hold_id": row.hold_id,
            "placed_at": row.placed_at.isoformat(),
            "amount": row.amount,
            "whole_account": row.whole_account,
        },
        "transactions": [
            {
                "txn_id": p.txn_id,
                "at": p.at.isoformat(),
                "direction": p.direction,
                "rail": p.rail,
                "reference": p.reference,
                "amount": p.amount,
                "counterparty": json.loads(p.counterparty) if p.counterparty else None,
                "exit": json.loads(p.exit) if p.exit else None,
            }
            for p in postings
            if p.at >= window_start
        ],
    }


def record_str_filed(session: Session, hold_id: str, *, now: datetime, actor: str, reference: str) -> HoldRow:
    row = _get(session, hold_id)
    if row.mule_confirmed_at is None:
        raise HoldError("an STR is drafted once the bank confirms the account is a mule")
    if row.str_filed_at is not None:
        raise HoldError("the STR for this hold is already recorded as filed")
    if not reference.strip():
        raise HoldError("give FINnet's acknowledgement reference for the STR")
    row.str_filed_at = now
    row.str_reference = reference.strip()[:64]
    _event(session, row, now, actor, "str_filed", reference=row.str_reference)
    return row


def deadlines(row: HoldRow, now: datetime) -> tuple[Deadline, ...]:
    def state(due: datetime, met: datetime | None) -> Literal["met", "open", "missed"]:
        if met is not None:
            return "met" if met <= due else "missed"
        return "open" if now <= due else "missed"

    items = [
        Deadline(
            name="Customer notified",
            due=row.placed_at,
            met_at=row.placed_at,
            state="met",
            rule="Annex III Step 2: at once when the customer is reached digitally",
        ),
        Deadline(
            name="Customer explanation",
            due=row.explanation_due,
            met_at=row.explanation_at,
            state="met" if row.explanation_at else ("open" if now <= row.explanation_due else "lapsed"),
            rule="Annex III Step 3: 20 days from the hold",
        ),
        Deadline(
            name="Bank decision",
            due=row.decision_due,
            met_at=row.decided_at,
            state=state(row.decision_due, row.decided_at),
            rule="Annex III Step 4: 10 days from an explanation, or 30 days from the hold without one",
        ),
    ]
    if row.reported_at is not None and row.instruction_at is None and row.expires_at is not None:
        items.append(
            Deadline(
                name="Release unless the police instruct otherwise",
                due=row.expires_at,
                met_at=row.released_at,
                state="met" if row.released_at else "open",
                rule="Annex III Step 6: the 31st day from the report, within 60 days of the hold",
            )
        )
    elif row.released_at is None and row.expires_at is not None:
        items.append(
            Deadline(
                name="Maximum duration",
                due=row.expires_at,
                met_at=None,
                state="open",
                rule="Annex III: no temporary debit hold lasts more than 60 days",
            )
        )
    if row.str_due is not None:
        items.append(
            Deadline(
                name="STR filed with FIU-IND",
                due=row.str_due,
                met_at=row.str_filed_at,
                state=state(row.str_due, row.str_filed_at),
                rule="PML Rules, rule 8(3): 7 working days from forming the suspicion",
            )
        )
    return tuple(items)


def view(session: Session, row: HoldRow, now: datetime) -> HoldView:
    account = session.get(Account, row.account_number)
    marks = deadlines(row, now)
    breach = None
    if row.str_due is not None and row.str_filed_at is None and now > row.str_due:
        breach = "A confirmed mule without a filed STR: the bank is not compliant (Amendment Directions para 4(1))."
    elif any(d.state == "missed" for d in marks):
        missed = next(d for d in marks if d.state == "missed")
        breach = f"Missed: {missed.name.lower()} was due {_when(missed.due)}."
    open_dues = [d.due for d in marks if d.state == "open"]
    return HoldView(
        hold_id=row.hold_id,
        account_number=row.account_number,
        holder_name=account.holder_name if account else "",
        whole_account=row.whole_account,
        amount=row.amount,
        credit_txns=tuple(json.loads(row.credit_txns)),
        reasons=tuple(json.loads(row.reasons)),
        account_level_reason=row.account_level_reason,
        contact=row.contact,
        customer_notice=row.customer_notice,
        status=row.status,
        placed_by=row.placed_by,
        placed_at=row.placed_at,
        explanation_at=row.explanation_at,
        explanation=row.explanation,
        decision=row.decision,
        decision_reason=row.decision_reason,
        reported_at=row.reported_at,
        instruction=row.instruction,
        expires_at=row.expires_at,
        released_at=row.released_at,
        release_reason=row.release_reason,
        mule_confirmed_at=row.mule_confirmed_at,
        str_due=row.str_due,
        str_filed_at=row.str_filed_at,
        str_reference=row.str_reference,
        str_draft=json.loads(row.str_draft) if row.str_draft else None,
        compliance_breach=breach,
        next_deadline=min(open_dues) if open_dues else None,
        deadlines=marks,
        notes=notes(session, row.hold_id),
    )


def add_note(session: Session, hold_id: str, *, now: datetime, actor: str, note: str) -> HoldRow:
    """A call, a document received, a reminder sent: kept in the audit log, so it is part of the hold's record."""
    row = _get(session, hold_id)
    _event(session, row, now, actor, "note", note=note.strip())
    return row


def notes(session: Session, hold_id: str) -> tuple[Note, ...]:
    rows = session.scalars(
        select(AuditEntry).where(AuditEntry.action == "hold.note").order_by(AuditEntry.seq)
    )
    found = []
    for r in rows:
        record = json.loads(r.record)
        if record.get("hold_id") == hold_id:
            found.append(Note(at=r.at, actor=r.actor, note=record.get("note", "")))
    return tuple(found)


def holds(session: Session, now: datetime) -> list[HoldView]:
    """Every hold, those in force first and nearest deadline first (the FRM analyst's queue)."""
    sweep(session, now)
    views = [view(session, r, now) for r in session.scalars(select(HoldRow))]
    far = datetime.max.replace(tzinfo=IST)
    return sorted(views, key=lambda v: (v.released_at is not None, v.next_deadline or far, v.placed_at))
