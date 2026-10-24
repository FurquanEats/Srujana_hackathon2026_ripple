"""Formatting for reason sentences shown to analysts."""

from __future__ import annotations

from datetime import timedelta


def inr(amount: float) -> str:
    """Indian digit grouping: 120000 -> 'Rs 1,20,000'."""
    whole = int(round(amount))
    sign = "-" if whole < 0 else ""
    digits = str(abs(whole))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return f"Rs {sign}{digits}"


def duration(span: timedelta) -> str:
    minutes = int(span.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    hours = minutes / 60
    if hours < 48:
        return f"{hours:.0f} hour" + ("" if round(hours) == 1 else "s")
    return f"{hours / 24:.0f} days"


def ids(txn_ids: list[str], limit: int = 4) -> str:
    if len(txn_ids) <= limit:
        return ", ".join(txn_ids)
    return f"{', '.join(txn_ids[:limit])} and {len(txn_ids) - limit} more"


def names(accounts: list[str]) -> str:
    if len(accounts) == 1:
        return accounts[0]
    return ", ".join(accounts[:-1]) + " and " + accounts[-1]
