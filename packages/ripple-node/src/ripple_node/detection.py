"""Red-flag rules for suspected mule accounts, and how a bank tunes them on its own history.

Each rule is a well-known mule pattern written so an officer can read it, with one setting the bank chooses (PRD,
"Detecting mule accounts, and how a bank sets the thresholds"). No model learns from any data. A flag never holds
money by itself: it opens a case for the FRM analyst, who decides whether to place RBI's temporary debit hold.

Only credits of Rs 1,000 or more are flagged, the floor in RBI's draft SOP on suspected money mule accounts
(Annex III, para 3(8)). Every flag cites the transactions behind it, so the reason can be checked line by line.

This module is pure: it works on plain records of one bank's own ledger, so the same code runs on each posting
and in the calibration replay over the bank's last 30 days.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum

from ripple_core.clock import IST
from ripple_core.money import fmt_inr, rupees

MIN_CREDIT = rupees(1_000)  # RBI draft SOP, Annex III para 3(8): transactions of Rs 1,000 and above
PASS_THROUGH_SHARE = 0.8  # "most of a credit leaves": 80% of it
CASH_OUT_SHARE = 0.5  # half a credit or more withdrawn in cash
DORMANT_BURST = rupees(25_000)  # the first large credit after a quiet spell
WINDOW = timedelta(days=30)  # how far back the profile and calibration rules look
NEW_SENDER_WINDOW = timedelta(hours=24)
CASH_MODES = frozenset({"atm", "aeps"})


class Rule(StrEnum):
    PASS_THROUGH = "pass_through"  # noqa: S105 - a rule name, not a password
    NEW_SENDERS = "many_new_senders"
    OUT_OF_PROFILE = "out_of_profile"
    DORMANT = "dormant_then_busy"
    CASH_OUT = "quick_cash_out"
    LINKED = "linked_to_reported"


RULE_TITLES = {
    Rule.PASS_THROUGH: "Pass-through",
    Rule.NEW_SENDERS: "Many new senders",
    Rule.OUT_OF_PROFILE: "Out of profile",
    Rule.DORMANT: "Dormant, then busy",
    Rule.CASH_OUT: "Quick cash-out",
    Rule.LINKED: "Linked to a reported account",
}


@dataclass(frozen=True)
class Thresholds:
    """The knob each bank sets for each rule. The defaults are a starting point for the shadow run, not advice."""

    pass_through_minutes: int = 30  # minutes until 80% of a credit has left
    new_senders: int = 5  # first-time senders in 24 hours
    profile_multiple: float = 3.0  # credits in 30 days as a multiple of declared monthly income or turnover
    dormant_days: int = 90  # days with no transaction before a large credit
    cash_out_minutes: int = 60  # minutes between a credit and cash withdrawals of half of it

    def value(self, rule: Rule) -> float | None:
        return {
            Rule.PASS_THROUGH: self.pass_through_minutes,
            Rule.NEW_SENDERS: self.new_senders,
            Rule.OUT_OF_PROFILE: self.profile_multiple,
            Rule.DORMANT: self.dormant_days,
            Rule.CASH_OUT: self.cash_out_minutes,
        }.get(rule)

    def with_value(self, rule: Rule, value: float) -> Thresholds:
        if rule is Rule.PASS_THROUGH:
            return replace(self, pass_through_minutes=int(value))
        if rule is Rule.NEW_SENDERS:
            return replace(self, new_senders=int(value))
        if rule is Rule.OUT_OF_PROFILE:
            return replace(self, profile_multiple=float(value))
        if rule is Rule.DORMANT:
            return replace(self, dormant_days=int(value))
        if rule is Rule.CASH_OUT:
            return replace(self, cash_out_minutes=int(value))
        raise ValueError(f"{rule.value} has no setting")


# The settings the shadow run tries for each rule, from least to most sensitive.
GRID: Mapping[Rule, tuple[float, ...]] = {
    Rule.PASS_THROUGH: (10, 30, 60, 180),
    Rule.NEW_SENDERS: (20, 10, 5, 3),
    Rule.OUT_OF_PROFILE: (5.0, 3.0, 2.0, 1.5),
    Rule.DORMANT: (180, 90, 60, 30),
    Rule.CASH_OUT: (15, 30, 60, 180),
}
TUNABLE = tuple(GRID)


@dataclass(frozen=True)
class Txn:
    """One posting as the rules see it."""

    txn_id: str
    at: datetime
    direction: str  # "credit" or "debit"
    amount: int
    counterparty: str | None = None  # a stable key for the other account, or None for an exit
    exit_mode: str | None = None


@dataclass(frozen=True)
class AccountFacts:
    account_number: str
    holder_name: str
    opened_at: datetime
    declared_annual_income: int | None  # KYC: income for a person, turnover for a business
    txns: tuple[Txn, ...]  # in ledger order


@dataclass(frozen=True)
class Flag:
    """One rule firing on one account, with the transactions it cites and a reason an officer can check."""

    rule: Rule
    account_number: str
    at: datetime  # when the pattern was complete
    credit_txns: tuple[str, ...]  # the credits of Rs 1,000 or more that a debit hold could cover
    cited_txns: tuple[str, ...]  # every transaction the reason names
    amount: int  # the flagged credits' total
    reason: str
    key: str = field(default="")  # stable identity, so a rescan never duplicates a flag

    def __post_init__(self) -> None:
        if not self.key:
            object.__setattr__(self, "key", f"{self.rule.value}:{self.account_number}:{self.credit_txns[0]}")


def _when(at: datetime) -> str:
    return at.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def _minutes(delta: timedelta) -> str:
    total = max(1, round(delta.total_seconds() / 60))
    return f"{total} minute{'s' if total != 1 else ''}"


def _credits(facts: AccountFacts) -> list[Txn]:
    return [t for t in facts.txns if t.direction == "credit" and t.amount >= MIN_CREDIT]


def pass_through(facts: AccountFacts, limit: int) -> list[Flag]:
    window = timedelta(minutes=limit)
    flags = []
    for credit in _credits(facts):
        out, cited = 0, []
        for t in facts.txns:
            if t.direction != "debit" or t.at < credit.at or t.at > credit.at + window:
                continue
            out += t.amount
            cited.append(t.txn_id)
            if out >= credit.amount * PASS_THROUGH_SHARE:
                gone = min(out, credit.amount) * 100 // credit.amount
                reason = (
                    f"{fmt_inr(credit.amount)} arrived on {_when(credit.at)}, and {gone}% of it left the account "
                    f"within {_minutes(t.at - credit.at)} in {len(cited)} debit{'s' if len(cited) != 1 else ''}."
                )
                flags.append(
                    Flag(
                        Rule.PASS_THROUGH,
                        facts.account_number,
                        t.at,
                        (credit.txn_id,),
                        (credit.txn_id, *cited),
                        credit.amount,
                        reason,
                    )
                )
                break
    return flags


def many_new_senders(facts: AccountFacts, limit: int) -> list[Flag]:
    seen: set[str] = set()
    recent: list[Txn] = []  # first-time credits in the last 24 hours
    flags: list[Flag] = []
    covered: set[str] = set()
    for t in facts.txns:
        if t.direction != "credit" or t.counterparty is None:
            continue
        first_time = t.counterparty not in seen
        seen.add(t.counterparty)
        if not first_time or t.amount < MIN_CREDIT:
            continue
        recent = [r for r in recent if r.at > t.at - NEW_SENDER_WINDOW] + [t]
        if len(recent) >= limit and recent[0].txn_id not in covered:
            covered.update(r.txn_id for r in recent)
            total = sum(r.amount for r in recent)
            reason = (
                f"{len(recent)} senders who had never paid this account before sent {fmt_inr(total)} between "
                f"{_when(recent[0].at)} and {_when(t.at)}."
            )
            ids = tuple(r.txn_id for r in recent)
            flags.append(Flag(Rule.NEW_SENDERS, facts.account_number, t.at, ids, ids, total, reason))
    return flags


def out_of_profile(facts: AccountFacts, multiple: float) -> list[Flag]:
    declared = facts.declared_annual_income
    if declared is None:
        return []  # nothing declared to compare against
    monthly = declared // 12
    big = _credits(facts)
    for i, t in enumerate(big):
        window = [c for c in big[: i + 1] if c.at > t.at - WINDOW]
        total = sum(c.amount for c in window)
        if total > monthly * multiple:
            ids = tuple(c.txn_id for c in window)
            if monthly == 0:
                compared = "the customer declared no income or turnover at account opening"
            else:
                compared = (
                    f"that is {total / monthly:.1f} times the declared monthly income or turnover of "
                    f"{fmt_inr(monthly)} ({fmt_inr(declared)} a year)"
                )
            reason = f"Credits of {fmt_inr(total)} arrived in the 30 days to {_when(t.at)}, and {compared}."
            return [Flag(Rule.OUT_OF_PROFILE, facts.account_number, t.at, ids, ids, total, reason)]
    return []


def dormant_then_busy(facts: AccountFacts, days: int) -> list[Flag]:
    quiet = timedelta(days=days)
    last = facts.opened_at
    flags = []
    for t in facts.txns:
        if t.direction == "credit" and t.amount >= DORMANT_BURST and t.at - last >= quiet:
            reason = (
                f"The account had no transactions for {(t.at - last).days} days, then received "
                f"{fmt_inr(t.amount)} on {_when(t.at)}."
            )
            flags.append(
                Flag(Rule.DORMANT, facts.account_number, t.at, (t.txn_id,), (t.txn_id,), t.amount, reason)
            )
        last = t.at
    return flags


def quick_cash_out(facts: AccountFacts, limit: int) -> list[Flag]:
    window = timedelta(minutes=limit)
    flags = []
    for credit in _credits(facts):
        cash, cited = 0, []
        for t in facts.txns:
            if t.exit_mode not in CASH_MODES or t.at < credit.at or t.at > credit.at + window:
                continue
            cash += t.amount
            cited.append(t.txn_id)
            if cash >= credit.amount * CASH_OUT_SHARE:
                reason = (
                    f"{fmt_inr(cash)} was withdrawn in cash in {len(cited)} withdrawal"
                    f"{'s' if len(cited) != 1 else ''} within {_minutes(t.at - credit.at)} of a "
                    f"{fmt_inr(credit.amount)} credit on {_when(credit.at)}."
                )
                flags.append(
                    Flag(
                        Rule.CASH_OUT,
                        facts.account_number,
                        t.at,
                        (credit.txn_id,),
                        (credit.txn_id, *cited),
                        credit.amount,
                        reason,
                    )
                )
                break
    return flags


def linked_to_reported(facts: AccountFacts, reported: Mapping[str, str]) -> list[Flag]:
    """`reported` maps a counterparty key to why it is reported (a CFCFRMS notice, a DPIP signal)."""
    flags = []
    for t in facts.txns:
        if t.counterparty is None or t.counterparty not in reported or t.amount < MIN_CREDIT:
            continue
        way = "from" if t.direction == "credit" else "to"
        reason = f"{fmt_inr(t.amount)} on {_when(t.at)} was {way} an account with {reported[t.counterparty]}."
        credit_ids = (t.txn_id,) if t.direction == "credit" else ()
        flags.append(
            Flag(
                Rule.LINKED,
                facts.account_number,
                t.at,
                credit_ids or (t.txn_id,),
                (t.txn_id,),
                t.amount if credit_ids else 0,
                reason,
            )
        )
    return flags


def scan(
    facts: AccountFacts,
    thresholds: Thresholds,
    reported: Mapping[str, str] | None = None,
    rules: Iterable[Rule] = tuple(Rule),
) -> list[Flag]:
    """Every rule's flags on one account, oldest first."""
    chosen = set(rules)
    found: list[Flag] = []
    if Rule.PASS_THROUGH in chosen:
        found += pass_through(facts, thresholds.pass_through_minutes)
    if Rule.NEW_SENDERS in chosen:
        found += many_new_senders(facts, thresholds.new_senders)
    if Rule.OUT_OF_PROFILE in chosen:
        found += out_of_profile(facts, thresholds.profile_multiple)
    if Rule.DORMANT in chosen:
        found += dormant_then_busy(facts, thresholds.dormant_days)
    if Rule.CASH_OUT in chosen:
        found += quick_cash_out(facts, thresholds.cash_out_minutes)
    if Rule.LINKED in chosen and reported:
        found += linked_to_reported(facts, reported)
    return sorted(found, key=lambda f: f.at)


# Calibration: the shadow run over the bank's own last 30 days (PRD, "How a bank sets the thresholds").


@dataclass(frozen=True)
class SettingResult:
    value: float
    accounts_flagged: int
    flags_per_day: float
    known_bad_flagged: int  # flagged accounts that carry an outcome the bank already knows


@dataclass(frozen=True)
class RuleTable:
    rule: Rule
    rows: tuple[SettingResult, ...]  # least to most sensitive
    chosen: float  # the proposal within the review budget


@dataclass(frozen=True)
class Calibration:
    since: datetime
    until: datetime
    accounts: int
    known_bad: int
    budget_per_day: float
    tables: tuple[RuleTable, ...]
    proposal: Thresholds
    expected_flags_per_day: float

    @property
    def within_budget(self) -> bool:
        """False when even the least sensitive settings flag more than the team can review; the FRM head must then
        raise the budget or accept a backlog."""
        return self.expected_flags_per_day <= self.budget_per_day

    @property
    def days(self) -> float:
        return max((self.until - self.since).total_seconds() / 86_400, 1.0)


def calibrate(
    accounts: Sequence[AccountFacts],
    known_bad: set[str],
    *,
    since: datetime,
    until: datetime,
    budget_per_day: float,
    start: Thresholds | None = None,
) -> Calibration:
    """Replay every rule at every setting over `since`..`until`, then propose the most sensitive settings whose
    flags fit the review budget.

    The proposal starts every rule at its least sensitive setting and repeatedly makes one rule one step more
    sensitive, choosing the step that catches the most extra known-bad accounts per extra flag a day, for as long
    as the total stays within the budget. The FRM head reviews the tables and approves or changes it.
    """
    days = max((until - since).total_seconds() / 86_400, 1.0)
    base = start or Thresholds()
    results: dict[Rule, list[tuple[SettingResult, frozenset[str]]]] = {}
    for rule, values in GRID.items():
        rows = []
        for value in values:
            settings = base.with_value(rule, value)
            flags = [
                f
                for facts in accounts
                for f in scan(facts, settings, rules=(rule,))
                if since <= f.at <= until
            ]
            flagged = frozenset(f.account_number for f in flags)
            rows.append(
                (
                    SettingResult(value, len(flagged), round(len(flags) / days, 2), len(flagged & known_bad)),
                    flagged,
                )
            )
        results[rule] = rows

    step = dict.fromkeys(GRID, 0)

    def load(choice: Mapping[Rule, int]) -> float:
        return sum(results[r][i][0].flags_per_day for r, i in choice.items())

    while True:
        best: tuple[float, Rule] | None = None
        for rule, i in step.items():
            if i + 1 >= len(results[rule]):
                continue
            trial = {**step, rule: i + 1}
            if load(trial) > budget_per_day:
                continue
            here, there = results[rule][i][0], results[rule][i + 1][0]
            extra_load = max(there.flags_per_day - here.flags_per_day, 0.01)
            gain = (there.known_bad_flagged - here.known_bad_flagged) / extra_load
            if best is None or gain > best[0]:
                best = (gain, rule)
        if best is None:
            break
        step[best[1]] += 1

    proposal = base
    for rule, i in step.items():
        proposal = proposal.with_value(rule, results[rule][i][0].value)
    tables = tuple(
        RuleTable(rule, tuple(r for r, _ in results[rule]), results[rule][step[rule]][0].value)
        for rule in GRID
    )
    return Calibration(
        since, until, len(accounts), len(known_bad), budget_per_day, tables, proposal, round(load(step), 2)
    )
