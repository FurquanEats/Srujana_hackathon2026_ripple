"""The payment check (PRD P1 and P2): before a customer's payment leaves, decide allow, warn, cooling hold, or hold
and call, with reasons.

Two kinds of evidence go in. About the payee: the DPIP answer the gateway fetched from the hub (the suspect
registry built from CFCFRMS trails, and risk signals other banks published), and, when the payee banks here, this
bank's own flags, holds and notices on that account. About the sender: the coerced-transfer pattern, where an
established customer sends most of a lump sum that just arrived to a payee they have never paid, at several times
their usual payment. Nothing is recorded and no money moves; the check only answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ripple_core.messages import AccountRef
from ripple_core.money import fmt_inr
from ripple_node import ledger, monitoring

Decision = Literal["allow", "warn", "cooling_hold", "hold_and_call"]
DpipLevel = Literal["none", "medium", "high", "very_high"]

LAKH = 1_00_000_00  # paise
LUMP_WINDOW = timedelta(hours=72)
HISTORY = timedelta(days=90)
ESTABLISHED = timedelta(days=180)
COOLING_MINUTES = 60


@dataclass(frozen=True)
class Reason:
    source: Literal["dpip", "this_bank", "sender"]
    text: str


@dataclass(frozen=True)
class CheckResult:
    decision: Decision
    headline: str
    reasons: tuple[Reason, ...]
    cooling_minutes: int | None
    payee_here: bool


def _payee_side(session: Session, payee: AccountRef, now: datetime) -> tuple[int, list[Reason], bool]:
    """Severity 0 to 3 from this bank's own records about the payee, if the payee banks here."""
    account = ledger.find_account(session, payee)
    if account is None:
        return 0, [], False
    reasons: list[Reason] = []
    severity = 0
    key = monitoring.ref_key(payee)
    reported = monitoring.reported_accounts(session)
    if key in reported:
        reasons.append(Reason("this_bank", f"The payee's account is named in {reported[key]} at this bank."))
        severity = 3
    active = [h for h in session.scalars(select(ledger.HoldRow).where(
        ledger.HoldRow.account_number == account.account_number)) if h.active_at(now)]  # fmt: skip
    if active:
        reasons.append(
            Reason("this_bank", "This bank has a temporary debit hold on the payee as a suspected mule.")
        )
        severity = 3
    open_flags = [c for c in monitoring.cases(session, now) if c.account_number == account.account_number]
    if open_flags and not active:
        titles = ", ".join(f.title.lower() for f in open_flags[0].flags)
        reasons.append(Reason("this_bank", f"This bank's mule rules flagged the payee ({titles})."))
        severity = max(severity, 2 if open_flags[0].priority == "high" else 1)
    return severity, reasons, True


def _sender_side(
    session: Session, sender: ledger.Account, payee: AccountRef, amount: int, now: datetime
) -> tuple[int, list[Reason]]:
    """Severity 0 to 2 from the coerced-transfer pattern on the sender's own history."""
    history = [p for p in ledger.postings(session, sender.account_number) if p.at <= now]
    key = monitoring.ref_key(payee)
    debits = [p for p in history if p.direction == "debit" and p.at >= now - HISTORY]
    paid_before = any(
        monitoring.ref_key(p.counterparty_ref()) == key for p in history if p.direction == "debit"
    )
    usual = median(p.amount for p in debits) if debits else 0
    multiple = amount / usual if usual else float("inf")
    lumps = [p for p in history if p.direction == "credit" and p.at >= now - LUMP_WINDOW]
    lump = max(lumps, key=lambda p: p.amount, default=None)
    established = now - sender.opened_at >= ESTABLISHED
    reasons: list[Reason] = []
    if not paid_before:
        reasons.append(Reason("sender", "The customer has never paid this payee before."))
    if usual and multiple >= 3:
        reasons.append(
            Reason(
                "sender",
                f"It is {multiple:.0f} times the customer's usual payment of {fmt_inr(int(usual))} "
                "over the last 90 days.",
            )
        )
    drains = lump is not None and amount >= 0.7 * lump.amount
    if drains and lump is not None:
        reasons.append(
            Reason(
                "sender",
                f"It sends on {amount / lump.amount:.0%} of {fmt_inr(lump.amount)} that arrived in the last 72 hours.",
            )
        )
    coerced = established and not paid_before and amount >= LAKH and multiple >= 5 and drains
    if coerced:
        return 2, reasons
    if not paid_before and amount >= LAKH // 2 and multiple >= 3:
        return 1, reasons
    return 0, reasons


def check(session: Session, *, sender_account: str, payee: AccountRef, amount: int, now: datetime,
          dpip_level: DpipLevel, dpip_reasons: tuple[str, ...]) -> CheckResult:  # fmt: skip
    sender = session.get(ledger.Account, sender_account)
    if sender is None:
        raise ledger.LedgerConflict(f"no account {sender_account} at this bank")
    reasons = [Reason("dpip", r) for r in dpip_reasons]
    dpip = {"none": 0, "medium": 1, "high": 3, "very_high": 3}[dpip_level]
    payee_severity, payee_reasons, payee_here = _payee_side(session, payee, now)
    sender_severity, sender_reasons = _sender_side(session, sender, payee, amount, now)
    reasons += payee_reasons + sender_reasons
    payee_risk = max(dpip, payee_severity)
    decision: Decision
    if payee_risk >= 3 or (payee_risk >= 1 and sender_severity >= 2):
        decision, headline = (
            "hold_and_call",
            "Hold the payment and call the customer: the payee is a reported or suspected mule.",
        )
    elif sender_severity >= 2:
        decision, headline = (
            "cooling_hold",
            (
                f"Hold the payment for {COOLING_MINUTES} minutes and call the customer or a trusted contact: "
                "this looks like a customer being coached to move their savings. The customer can release it."
            ),
        )
    elif payee_risk >= 1 or sender_severity >= 1:
        decision, headline = "warn", "Show the customer a warning before they confirm."
    else:
        decision, headline = "allow", "Nothing points to fraud. Let the payment go."
    return CheckResult(
        decision,
        headline,
        tuple(reasons),
        COOLING_MINUTES if decision == "cooling_hold" else None,
        payee_here,
    )
