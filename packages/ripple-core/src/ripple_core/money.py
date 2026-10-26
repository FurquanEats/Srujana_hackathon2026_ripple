"""Money as whole paise.

Every amount in Ripple is an `int` number of paise, so sums and splits are exact. Floats never touch money.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import NewType

Paise = NewType("Paise", int)

PAISE_PER_RUPEE = 100


def rupees(amount: int | str | Decimal) -> Paise:
    """Convert a rupee amount such as 250000 or "2,50,000.50" to paise, rejecting fractions of a paisa."""
    text = str(amount).replace(",", "").strip()
    try:
        value = Decimal(text) * PAISE_PER_RUPEE
    except InvalidOperation as exc:
        raise ValueError(f"not a rupee amount: {amount!r}") from exc
    if value != value.to_integral_value():
        raise ValueError(f"amount has a fraction of a paisa: {amount!r}")
    return Paise(int(value))


def fmt_inr(paise: int) -> str:
    """Format paise the Indian way: 25000000 -> "₹2,50,000", 4069508 -> "₹40,695.08"."""
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), PAISE_PER_RUPEE)
    digits = str(whole)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{sign}₹{digits}" + (f".{frac:02d}" if frac else "")


def split_pro_rata[K](total: int, weights: Mapping[K, int]) -> dict[K, int]:
    """Split `total` paise across `weights` in proportion, with the parts adding up to `total` exactly.

    Each part is first rounded half up, as a person would do by hand (this gives the SOP's own Annexure V figures).
    If rounding leaves the parts a paisa or two away from the total, the difference goes to the parts whose
    rounding moved them furthest, largest weight first, so the result does not depend on dictionary order.
    """
    if total < 0:
        raise ValueError("cannot split a negative amount")
    weight_sum = sum(weights.values())
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must not be negative")
    if weight_sum == 0:
        if total:
            raise ValueError("cannot split a positive amount over zero weights")
        return dict.fromkeys(weights, 0)
    exact = {k: Decimal(total) * w / weight_sum for k, w in weights.items()}
    parts = {k: int(v.quantize(Decimal(1), rounding=ROUND_HALF_UP)) for k, v in exact.items()}
    gap = total - sum(parts.values())
    if gap:
        step = 1 if gap > 0 else -1
        # Fix the parts whose rounding moved them furthest in the wrong direction first.
        order = sorted(weights, key=lambda k: ((exact[k] - parts[k]) * step, weights[k]), reverse=True)
        for k in order[: abs(gap)]:
            parts[k] += step
    return parts
