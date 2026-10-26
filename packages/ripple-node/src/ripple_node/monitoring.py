"""Transaction monitoring on the bank's own ledger: run the red-flag rules, keep their flags as cases for the FRM
analyst, and hold the settings the bank approved after its shadow run.

The node rescans an account whenever new postings reach it, so a flag appears as soon as its pattern is complete.
Flags only open cases. The analyst places RBI's temporary debit hold (`ripple_node.holds`) or dismisses the case
with a reason, because legitimate customers also behave unusually.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from ripple_core.messages import AccountRef
from ripple_node import detection, ledger
from ripple_node.detection import AccountFacts, Calibration, Flag, Rule, Thresholds, Txn
from ripple_node.ledger import Account, HoldRow, NodeBase, NoticeRow, Posting
from ripple_service.db import UtcDateTime, append_audit

KNOWN_OUTCOME_WINDOW = timedelta(days=365)  # outcomes the bank already holds: the past 12 months
HIGH_RULES = 3  # this many different rules on one account makes a case high priority


class FlagRow(NodeBase):
    __tablename__ = "mule_flags"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    account_number: Mapped[str] = mapped_column(ForeignKey("accounts.account_number"), index=True)
    rule: Mapped[str] = mapped_column(String(32))
    at: Mapped[datetime] = mapped_column(UtcDateTime(), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    credit_txns: Mapped[str] = mapped_column(Text)  # JSON list
    cited_txns: Mapped[str] = mapped_column(Text)  # JSON list
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open, held, dismissed
    dismissed_by: Mapped[str | None] = mapped_column(String(64))
    dismissed_reason: Mapped[str | None] = mapped_column(Text)
    flagged_at: Mapped[datetime] = mapped_column(UtcDateTime())


class ThresholdRow(NodeBase):
    """Each approved set of settings, kept so every choice is on record (who, when, and on what budget)."""

    __tablename__ = "mule_thresholds"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    settings: Mapped[str] = mapped_column(Text)  # JSON of Thresholds
    budget_per_day: Mapped[float | None] = mapped_column(Float)
    approved_by: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = mapped_column(UtcDateTime())


class View(BaseModel):
    model_config = ConfigDict(frozen=True)


class FlagView(View):
    key: str
    rule: Rule
    title: str
    at: datetime
    amount: int
    credit_txns: tuple[str, ...]
    cited_txns: tuple[str, ...]
    reason: str
    status: str
    dismissed_reason: str | None


class CaseView(View):
    """Everything flagged on one account, with a priority the analyst can sort by."""

    account_number: str
    holder_name: str
    declared_profile: str
    declared_annual_income: int | None
    priority: str  # high, medium or low
    priority_reason: str
    rules: tuple[Rule, ...]
    flagged_amount: int
    first_at: datetime
    last_at: datetime
    reported: bool  # the account itself has a CFCFRMS notice
    active_hold_id: str | None
    flags: tuple[FlagView, ...]


def ref_key(ref: AccountRef | None) -> str | None:
    if ref is None:
        return None
    if ref.account_number is not None:
        return f"{ref.ifsc}:{ref.account_number}"
    return f"vpa:{ref.vpa}"


def facts_for(session: Session, account: Account, *, until: datetime | None = None) -> AccountFacts:
    txns = []
    for p in ledger.postings(session, account.account_number):
        if until is not None and p.at > until:
            break
        detail = p.exit_detail()
        txns.append(
            Txn(
                p.txn_id,
                p.at,
                p.direction,
                p.amount,
                ref_key(p.counterparty_ref()),
                detail.mode.value if detail else None,
            )
        )
    return AccountFacts(
        account.account_number,
        account.holder_name,
        account.opened_at,
        account.declared_annual_income,
        tuple(txns),
    )


def reported_accounts(session: Session) -> dict[str, str]:
    """Counterparty keys this bank knows are reported: its own accounts named in CFCFRMS notices."""
    reported: dict[str, str] = {}
    for row in session.scalars(select(NoticeRow).where(NoticeRow.account_number.is_not(None))):
        account = session.get(Account, row.account_number)
        if account is None:
            continue
        why = f"a CFCFRMS notice (acknowledgement {row.ack_number})"
        reported[f"{account.ifsc}:{account.account_number}"] = why
        if account.vpa:
            reported[f"vpa:{account.vpa}"] = why
    return reported


def current_thresholds(session: Session) -> Thresholds:
    row = session.scalars(select(ThresholdRow).order_by(ThresholdRow.seq.desc()).limit(1)).first()
    return Thresholds(**json.loads(row.settings)) if row else Thresholds()


def threshold_history(session: Session) -> list[dict[str, object]]:
    """Every approved set of settings, newest first, with who approved it and on what review budget."""
    rows = session.scalars(select(ThresholdRow).order_by(ThresholdRow.seq.desc()))
    return [
        {"settings": json.loads(r.settings), "budget_per_day": r.budget_per_day, "approved_by": r.approved_by,
         "approved_at": r.approved_at.isoformat()}
        for r in rows
    ]  # fmt: skip


def approve_thresholds(
    session: Session, settings: Thresholds, *, actor: str, now: datetime, budget_per_day: float | None
) -> ThresholdRow:
    row = ThresholdRow(
        settings=json.dumps(asdict(settings)),
        budget_per_day=budget_per_day,
        approved_by=actor,
        approved_at=now,
    )
    session.add(row)
    session.flush()
    append_audit(
        session, now, actor, "thresholds.approve", {**asdict(settings), "budget_per_day": budget_per_day}
    )
    return row


def rescan(session: Session, account_numbers: Iterable[str], now: datetime) -> list[FlagRow]:
    """Run every rule on these accounts and keep any new flag. A flag already kept is never duplicated."""
    thresholds = current_thresholds(session)
    reported = reported_accounts(session)
    added = []
    for number in sorted(set(account_numbers)):
        account = session.get(Account, number)
        if account is None:
            continue
        for flag in detection.scan(facts_for(session, account), thresholds, reported):
            if session.get(FlagRow, flag.key) is not None:
                continue
            added.append(_store(session, flag, now))
    return added


def _store(session: Session, flag: Flag, now: datetime) -> FlagRow:
    row = FlagRow(
        key=flag.key,
        account_number=flag.account_number,
        rule=flag.rule.value,
        at=flag.at,
        amount=flag.amount,
        credit_txns=json.dumps(flag.credit_txns),
        cited_txns=json.dumps(flag.cited_txns),
        reason=flag.reason,
        status="open",
        flagged_at=now,
    )
    session.add(row)
    session.flush()
    return row


def _flag_view(row: FlagRow) -> FlagView:
    rule = Rule(row.rule)
    return FlagView(
        key=row.key,
        rule=rule,
        title=detection.RULE_TITLES[rule],
        at=row.at,
        amount=row.amount,
        credit_txns=tuple(json.loads(row.credit_txns)),
        cited_txns=tuple(json.loads(row.cited_txns)),
        reason=row.reason,
        status=row.status,
        dismissed_reason=row.dismissed_reason,
    )


def cases(session: Session, now: datetime, *, include_closed: bool = False) -> list[CaseView]:
    """One case per flagged account: high priority first, then the most recent."""
    rows = list(session.scalars(select(FlagRow).order_by(FlagRow.at)))
    by_account: dict[str, list[FlagRow]] = {}
    for row in rows:
        by_account.setdefault(row.account_number, []).append(row)
    noticed = {r.account_number for r in session.scalars(select(NoticeRow)) if r.account_number}
    result = []
    for number, flags in by_account.items():
        open_flags = [f for f in flags if f.status != "dismissed"]
        if not open_flags and not include_closed:
            continue
        shown = open_flags or flags
        account = session.get(Account, number)
        if account is None:
            continue
        rules = tuple(dict.fromkeys(Rule(f.rule) for f in shown))
        hold = next(
            (
                h
                for h in session.scalars(select(HoldRow).where(HoldRow.account_number == number))
                if h.active_at(now)
            ),
            None,
        )
        priority, why = _priority(rules, reported=number in noticed)
        credit_ids = {t for f in shown for t in json.loads(f.credit_txns)}
        amounts = {p.txn_id: p.amount for p in ledger.postings(session, number) if p.txn_id in credit_ids}
        result.append(
            CaseView(
                account_number=number,
                holder_name=account.holder_name,
                declared_profile=account.declared_profile,
                declared_annual_income=account.declared_annual_income,
                priority=priority,
                priority_reason=why,
                rules=rules,
                flagged_amount=sum(amounts.values()),
                first_at=shown[0].at,
                last_at=shown[-1].at,
                reported=number in noticed,
                active_hold_id=hold.hold_id if hold else None,
                flags=tuple(_flag_view(f) for f in shown),
            )
        )
    rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(result, key=lambda c: (rank[c.priority], -c.last_at.timestamp()))


def _priority(rules: tuple[Rule, ...], *, reported: bool) -> tuple[str, str]:
    if Rule.LINKED in rules or reported:
        return "high", "Money moved to or from an account with a CFCFRMS notice, or this account has one."
    if len(rules) >= HIGH_RULES:
        return "high", f"{len(rules)} different red flags on one account."
    if len(rules) == 2:
        return "medium", "Two different red flags on one account."
    return "low", "One red flag. A single unusual pattern is often legitimate."


def dismiss(session: Session, account_number: str, *, actor: str, reason: str, now: datetime) -> int:
    """Close an account's open flags as legitimate, with the analyst's reason on record."""
    rows = list(
        session.scalars(
            select(FlagRow).where(FlagRow.account_number == account_number, FlagRow.status == "open")
        )
    )
    for row in rows:
        row.status = "dismissed"
        row.dismissed_by = actor
        row.dismissed_reason = reason
    append_audit(
        session,
        now,
        actor,
        "flags.dismiss",
        {"account": account_number, "flags": len(rows), "reason": reason},
    )
    return len(rows)


def known_bad(session: Session, now: datetime) -> set[str]:
    """Accounts the bank already knows turned out bad: CFCFRMS notices in the past 12 months, and confirmed mules."""
    since = now - KNOWN_OUTCOME_WINDOW
    noticed = {
        r.account_number
        for r in session.scalars(select(NoticeRow).where(NoticeRow.received_at >= since))
        if r.account_number
    }
    confirmed = {
        h.account_number
        for h in session.scalars(select(HoldRow).where(HoldRow.mule_confirmed_at.is_not(None)))
    }
    return noticed | confirmed


def shadow_run(session: Session, now: datetime, budget_per_day: float) -> Calibration:
    """Replay the bank's last 30 days through every rule at every setting. Nothing is held during this run."""
    accounts = list(session.scalars(select(Account)))
    since = now - detection.WINDOW
    facts = [facts_for(session, a, until=now) for a in accounts]
    active = [f for f in facts if any(t.at >= since for t in f.txns)]
    return detection.calibrate(
        active, known_bad(session, now), since=since, until=now, budget_per_day=budget_per_day
    )


def touched_accounts(postings: Iterable[Posting]) -> set[str]:
    return {p.account_number for p in postings}
